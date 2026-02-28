"""
实时交易执行服务
"""
import time
import threading
import traceback
import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json
from app.utils.logger import get_logger
from app.strategies.factory import load_and_create
from app.strategies.base import sleep_until_next_tick
from app.services.data_handler import DataHandler
from app.data_sources import DataSourceFactory
from app.services.kline import KlineService
from app.utils.console import console_print

logger = get_logger(__name__)


class TradingExecutor:
    """实时交易执行器 (Signal Provider Mode)"""

    def __init__(self):
        # 不再使用全局连接，改为每次使用时从连接池获取
        self.running_strategies = {}  # {strategy_id: thread}
        self.lock = threading.Lock()
        # Local-only lightweight in-memory price cache (symbol -> (price, expiry_ts)).
        # This replaces the old Redis-based PriceCache for local deployments.
        self._price_cache = {}
        self._price_cache_lock = threading.Lock()
        # Default to 10s to match the unified tick cadence.
        self._price_cache_ttl_sec = int(os.getenv("PRICE_CACHE_TTL_SEC", "10"))

        # In-memory signal de-dup cache to prevent repeated orders on the same candle signal.
        # Keyed by (strategy_id, symbol, signal_type, signal_timestamp).
        self._signal_dedup = {}  # type: Dict[int, Dict[str, float]]
        self._signal_dedup_lock = threading.Lock()
        self.kline_service = KlineService()   # K线服务（带缓存）
        self.data_handler = DataHandler(kline_service=self.kline_service)

        # 单实例线程上限，避免无限制创建线程导致 can't start new thread/OOM
        self.max_threads = int(os.getenv('STRATEGY_MAX_THREADS', '64'))
        logger.info(
            "TradingExecutor max_threads=%d (set STRATEGY_MAX_THREADS in .env if needed)",
            self.max_threads,
        )

        # 确保数据库字段存在
        self.data_handler.ensure_db_columns()

    def _normalize_trade_symbol(
        self, exchange: Any, symbol: str, market_type: str, exchange_id: str
    ) -> str:
        """
        将数据库/配置里的 symbol 规范化为交易所合约可用的 CCXT symbol。

        典型场景：OKX 永续统一符号通常是 `BNB/USDT:USDT`，但前端/数据库可能传 `BNB/USDT`。
        """
        try:
            # 新系统：仅支持 swap(合约永续) / spot(现货)
            if market_type != 'swap':
                return symbol
            if not symbol or ':' in symbol:
                return symbol
            if not getattr(exchange, 'markets', None):
                return symbol

            # 如果 symbol 本身就是合约市场，直接返回
            try:
                m = exchange.market(symbol)
                if m and (m.get('swap') or m.get('future') or m.get('contract')):
                    return symbol
            except Exception:
                pass

            # OKX/部分交易所：永续常见为 BASE/QUOTE:QUOTE 或 BASE/QUOTE:USDT
            if '/' not in symbol:
                return symbol
            base, quote = symbol.split('/', 1)
            candidates = []
            if quote:
                candidates.append(f"{base}/{quote}:{quote}")
                if quote.upper() != 'USDT':
                    candidates.append(f"{base}/{quote}:USDT")

            for cand in candidates:
                if cand in exchange.markets:
                    cm = exchange.markets[cand]
                    if cm and (cm.get('swap') or cm.get('future') or cm.get('contract')):
                        logger.info(
                            "symbol normalized: %s -> %s (exchange=%s, market_type=%s)",
                            symbol,
                            cand,
                            exchange_id,
                            market_type,
                        )
                        return cand

            return symbol
        except Exception:
            return symbol

    def _log_resource_status(self, prefix: str = ""):
        """调试：记录线程/内存使用，便于定位 can't start new thread 根因"""
        try:
            import psutil  # 如果有安装则使用更精确的指标
            p = psutil.Process()
            mem = p.memory_info().rss / 1024 / 1024
            th = p.num_threads()
            logger.warning(
                "%sresource status: memory=%.1fMB, threads=%s, running_strategies=%d",
                prefix,
                mem,
                th,
                len(self.running_strategies),
            )
        except Exception:
            try:
                th = threading.active_count()
                # 从 /proc/self/status 读取 VmRSS（适用于 Linux 容器）
                vmrss = None
                try:
                    with open('/proc/self/status', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('VmRSS:'):
                                vmrss = line.split()[1:3]  # e.g. ['123456', 'kB']
                                break
                except Exception:
                    pass
                vmrss_str = f"{vmrss[0]}{vmrss[1]}" if vmrss else "N/A"
                logger.warning(
                    "%sresource status: VmRSS=%s, active_threads=%s, running_strategies=%d",
                    prefix,
                    vmrss_str,
                    th,
                    len(self.running_strategies),
                )
            except Exception:
                pass

    def _console_print(self, msg: str) -> None:
        """Local-only observability: 委托给公共 console_print"""
        console_print(msg)

    def _position_state(self, positions: List[Dict[str, Any]]) -> str:
        """
        Return current position state for a strategy+symbol in local single-position mode.

        Returns: 'flat' | 'long' | 'short'
        """
        try:
            if not positions:
                return "flat"
            # Local mode assumes single-direction position per symbol.
            side = (positions[0].get("side") or "").strip().lower()
            if side in ("long", "short"):
                return side
        except Exception:
            pass
        return "flat"

    def _is_signal_allowed(self, state: str, signal_type: str) -> bool:
        """
        Enforce strict state machine:
        - flat: only open_long/open_short
        - long: only add_long/close_long
        - short: only add_short/close_short
        """
        st = (state or "flat").strip().lower()
        sig = (signal_type or "").strip().lower()
        if st == "flat":
            return sig in ("open_long", "open_short")
        if st == "long":
            return sig in ("add_long", "reduce_long", "close_long")
        if st == "short":
            return sig in ("add_short", "reduce_short", "close_short")
        return False

    def _signal_priority(self, signal_type: str) -> int:
        """
        Lower value = higher priority. We always close before (re)opening/adding.
        """
        sig = (signal_type or "").strip().lower()
        if sig.startswith("close_"):
            return 0
        if sig.startswith("reduce_"):
            return 1
        if sig.startswith("open_"):
            return 2
        if sig.startswith("add_"):
            return 3
        return 99

    def _dedup_key(self, strategy_id: int, symbol: str, signal_type: str, signal_ts: int) -> str:
        sym = (symbol or "").strip().upper()
        if ":" in sym:
            sym = sym.split(":", 1)[0]
        return f"{int(strategy_id)}|{sym}|{(signal_type or '').strip().lower()}|{int(signal_ts or 0)}"

    def _should_skip_signal_once_per_candle(
        self,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        signal_ts: int,
        timeframe_seconds: int,
        now_ts: Optional[int] = None,
    ) -> bool:
        """
        Prevent repeated orders for the same candle signal across ticks.

        This is especially important for 'confirmed' signals that point to the previous closed candle:
        the signal timestamp stays constant for the entire next candle, so without de-dup the system
        would re-enqueue the same order every tick.
        """
        try:
            now = int(now_ts or time.time())
            tf = int(timeframe_seconds or 0)
            if tf <= 0:
                tf = 60
            # Keep keys long enough to cover at least the next candle.
            ttl_sec = max(tf * 2, 120)
            expiry = float(now + ttl_sec)
            key = self._dedup_key(strategy_id, symbol, signal_type, int(signal_ts or 0))

            with self._signal_dedup_lock:
                bucket = self._signal_dedup.get(int(strategy_id))
                if bucket is None:
                    bucket = {}
                    self._signal_dedup[int(strategy_id)] = bucket

                # Opportunistic cleanup
                stale = [k for k, exp in bucket.items() if float(exp) <= now]
                for k in stale[:512]:
                    try:
                        del bucket[k]
                    except Exception:
                        pass

                exp = bucket.get(key)
                if exp is not None and float(exp) > now:
                    return True

                # Reserve the key (best-effort). Caller may still fail to enqueue; that's acceptable
                # because repeated failures should not flood the queue.
                bucket[key] = expiry
                return False
        except Exception:
            return False

    def _to_ratio(self, v: Any, default: float = 0.0) -> float:
        """
        Convert a percent-like value into ratio in [0, 1].
        Accepts both 0~1 and 0~100 inputs.
        """
        try:
            x = float(v if v is not None else default)
        except (ValueError, TypeError):
            x = float(default or 0.0)
        if x > 1.0:
            x = x / 100.0
        if x < 0:
            x = 0.0
        if x > 1.0:
            x = 1.0
        return float(x)

    def start_strategy(self, strategy_id: int) -> bool:
        """
        启动策略

        Args:
            strategy_id: 策略ID

        Returns:
            是否成功
        """
        try:
            with self.lock:
                # 清理已退出的线程，防止计数膨胀
                stale_ids = [sid for sid, th in self.running_strategies.items() if not th.is_alive()]
                for sid in stale_ids:
                    del self.running_strategies[sid]

                if len(self.running_strategies) >= self.max_threads:
                    logger.error(
                        "Thread limit reached (running=%d, max=%d); refuse to start strategy %d. "
                        "Reduce running strategies or set STRATEGY_MAX_THREADS in backend_api_python/.env",
                        len(self.running_strategies), self.max_threads, strategy_id,
                    )
                    self._log_resource_status(prefix="start_denied: ")
                    return False

                if strategy_id in self.running_strategies:
                    logger.warning("Strategy %s is already running", strategy_id)
                    return False

                # 创建并启动线程
                thread = threading.Thread(
                    target=self._run_strategy_loop,
                    args=(strategy_id,),
                    daemon=True
                )
                try:
                    thread.start()
                except Exception as e:
                    # 捕获 can't start new thread 等异常，记录资源状态
                    self._log_resource_status(prefix="启动异常")
                    raise e
                self.running_strategies[strategy_id] = thread

                logger.info("Strategy %s started", strategy_id)
                self._console_print(f"[strategy:{strategy_id}] started")
                return True

        except Exception as e:
            logger.error("Failed to start strategy %s: %s", strategy_id, e)
            logger.error(traceback.format_exc())
            return False

    def stop_strategy(self, strategy_id: int) -> bool:
        """
        停止策略

        Args:
            strategy_id: 策略ID

        Returns:
            是否成功
        """
        try:
            with self.lock:
                if strategy_id not in self.running_strategies:
                    logger.warning("Strategy %s is not running", strategy_id)
                    return False

                # 标记策略为停止状态
                self.data_handler.update_strategy_status(strategy_id, "stopped")

                # 从运行列表中移除（线程会在下次循环检查状态时退出）
                del self.running_strategies[strategy_id]

                logger.info("Strategy %s stopped", strategy_id)
                self._console_print(f"[strategy:{strategy_id}] stopped (requested)")
                return True

        except Exception as e:
            logger.error("Failed to stop strategy %s: %s", strategy_id, e)
            logger.error(traceback.format_exc())
            return False

    def _run_strategy_loop(self, strategy_id: int):
        """
        策略运行循环

        Args:
            strategy_id: 策略ID
        """
        logger.info("Strategy %s loop starting", strategy_id)
        self._console_print(f"[strategy:{strategy_id}] loop initializing")

        try:
            strat, strategy = load_and_create(strategy_id)
            if not strat or not strategy:
                logger.error("Strategy %s not found or invalid", strategy_id)
                return

            exchange = None  # 信号模式下无需真实连接

            cs_type = (strategy.get("trading_config") or {}).get("cs_strategy_type", "single")
            if cs_type == "cross_sectional":
                self._run_cross_sectional_loop(strat, strategy_id, strategy, exchange)
            else:
                self._run_single_symbol_loop(strat, strategy_id, strategy, exchange)

        except Exception as e:
            logger.error("Strategy %s crashed: %s", strategy_id, e)
            logger.error(traceback.format_exc())
            self._console_print(f"[strategy:{strategy_id}] fatal error: {e}")
        finally:
            # 清理
            with self.lock:
                if strategy_id in self.running_strategies:
                    del self.running_strategies[strategy_id]
            self._console_print(f"[strategy:{strategy_id}] loop exited")
            logger.info("Strategy %s loop exited", strategy_id)

    def _run_single_symbol_loop(
        self,
        strat: Any,
        strategy_id: int,
        strategy: Dict[str, Any],
        exchange: Any,
    ) -> None:
        """Executor 驱动的单标策略循环：调用 strategy.get_signals 获取信号，再执行"""
        trading_config = strategy.get("trading_config") or {}
        symbol = trading_config.get("symbol", "")
        market_type = strategy["_market_type"]
        market_category = strategy["_market_category"]
        try:
            tick_interval_sec = int(os.getenv("STRATEGY_TICK_INTERVAL_SEC", "10"))
        except (ValueError, TypeError):
            tick_interval_sec = 10
        if tick_interval_sec < 1:
            tick_interval_sec = 1

        last_tick_time = 0.0

        while True:
            try:
                if not self._is_strategy_running(strategy_id):
                    logger.info("Strategy %s stopped", strategy_id)
                    break
                current_time = time.time()
                should_continue, last_tick_time = sleep_until_next_tick(
                    current_time, last_tick_time, tick_interval_sec
                )
                if should_continue:
                    continue

                current_price = self._fetch_current_price(
                    exchange, symbol, market_type=market_type, market_category=market_category
                )
                if current_price is None:
                    logger.warning(
                        "Strategy %s failed to fetch current price for %s:%s",
                        strategy_id, market_category, symbol,
                    )
                    continue

                request = strat.get_data_request(strategy_id, strategy, current_time)
                ctx = self.data_handler.get_input_context_single(
                    strategy_id, request, current_price=float(current_price)
                )
                if ctx is None:
                    logger.warning("Strategy %s failed to get input context", strategy_id)
                    continue

                ctx["strategy_id"] = strategy_id
                ctx["indicator_code"] = strategy.get("_indicator_code", "")
                ctx["current_time"] = current_time
                ctx["current_price"] = float(current_price)

                triggered_signals, keep_running, _, meta = strat.get_signals(ctx)
                if not keep_running:
                    logger.warning("Strategy %s get_signals returned stop", strategy_id)
                    break

                if meta and meta.get("position_updates"):
                    for pu in meta["position_updates"]:
                        self.data_handler.update_position(
                            strategy_id=strategy_id,
                            symbol=pu["symbol"],
                            side=pu["side"],
                            size=pu["size"],
                            entry_price=pu["entry_price"],
                            current_price=pu["current_close"],
                            highest_price=pu["highest_price"],
                        )

                if triggered_signals:
                    self._process_and_execute_signals(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        triggered_signals=triggered_signals,
                        current_price=float(current_price),
                        strategy_name=strategy["_strategy_name"],
                        exchange=exchange,
                        trade_direction=(
                            "long"
                            if market_type == "spot"
                            else (trading_config.get("trade_direction") or "long")
                        ),
                        leverage=strategy["_leverage"],
                        initial_capital=strategy["_initial_capital"],
                        market_type=market_type,
                        market_category=market_category,
                        execution_mode=strategy["_execution_mode"],
                        notification_config=strategy.get("_notification_config"),
                        trading_config=trading_config,
                        ai_model_config=strategy.get("ai_model_config"),
                        timeframe_seconds=self._get_timeframe_seconds(trading_config.get("timeframe", "1H")),
                    )

                self.data_handler.update_positions_current_price(strategy_id, symbol, current_price)
                pending_count = len(strat._state.get("pending_signals", []))
                self._console_print(
                    f"[strategy:{strategy_id}] tick price={float(current_price or 0.0):.8f} pending_signals={pending_count}"
                )
            except Exception as e:
                logger.error("Strategy %s loop error: %s", strategy_id, e)
                logger.error(traceback.format_exc())
                self._console_print(f"[strategy:{strategy_id}] loop error: {e}")
                time.sleep(5)

        logger.info("Strategy %s loop exited", strategy_id)

    def _run_cross_sectional_loop(
        self,
        strat: Any,
        strategy_id: int,
        strategy: Dict[str, Any],
        exchange: Any,
    ) -> None:
        """Executor 驱动的截面策略循环：调用 strategy.get_signals 获取信号，再执行"""
        trading_config = strategy.get("trading_config") or {}
        tick_interval_sec = int(trading_config.get("decide_interval", 300))
        if tick_interval_sec < 1:
            tick_interval_sec = 300
        last_tick_time = 0.0

        while True:
            try:
                if not self._is_strategy_running(strategy_id):
                    logger.info("Cross-sectional strategy %s stopped", strategy_id)
                    break
                current_time = time.time()
                should_continue, last_tick_time = sleep_until_next_tick(
                    current_time, last_tick_time, tick_interval_sec
                )
                if should_continue:
                    continue

                request = strat.get_data_request(strategy_id, strategy, current_time)
                if not self._should_rebalance(strategy_id, request.get("rebalance_frequency", "daily")):
                    continue

                ctx = self.data_handler.get_input_context_cross(strategy_id, request)
                if ctx is None:
                    logger.warning("Strategy %s failed to get cross input context", strategy_id)
                    continue

                ctx["strategy_id"] = strategy_id
                ctx["indicator_code"] = strategy.get("_indicator_code", "")
                ctx["current_time"] = current_time

                signals, keep_running, update_rebalance, _ = strat.get_signals(ctx)
                if not keep_running:
                    break
                if signals:
                    self._execute_cross_sectional_signals(
                        strategy_id=strategy_id,
                        strategy=strategy,
                        signals=signals,
                        current_time=int(current_time),
                    )
                if update_rebalance:
                    self.data_handler.update_last_rebalance(strategy_id)

            except Exception as e:
                logger.error("Cross-sectional strategy %s loop error: %s", strategy_id, e)
                logger.error(traceback.format_exc())
                self._console_print(f"[strategy:{strategy_id}] loop error: {e}")
                time.sleep(5)

        logger.info("Cross-sectional strategy %s loop exited", strategy_id)

    def _execute_cross_sectional_signals(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        signals: List[Dict[str, Any]],
        current_time: int,
    ) -> None:
        """执行截面策略的批量信号（ThreadPoolExecutor）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        trading_config = strategy.get("trading_config") or {}
        positions = self.data_handler.get_all_positions(strategy_id)
        strategy_name = strategy["_strategy_name"]
        leverage = strategy["_leverage"]
        initial_capital = strategy["_initial_capital"]
        market_type = strategy["_market_type"]
        market_category = strategy["_market_category"]
        execution_mode = strategy["_execution_mode"]
        notification_config = strategy.get("_notification_config") or {}
        ai_model_config = strategy.get("ai_model_config")

        with ThreadPoolExecutor(max_workers=min(10, len(signals))) as pool:
            futures = {}
            for signal in signals:
                sig_symbol = (signal.get("symbol") or "")
                symbol_positions = [
                    p for p in positions
                    if (p.get("symbol") or "").split(":")[0] == sig_symbol.split(":")[0]
                ]
                future = pool.submit(
                    self._execute_signal,
                    strategy_id=strategy_id,
                    strategy_name=strategy_name,
                    exchange=None,
                    symbol=signal["symbol"],
                    current_price=0.0,
                    signal_type=signal["type"],
                    position_size=None,
                    current_positions=symbol_positions,
                    trade_direction="both",
                    leverage=leverage,
                    initial_capital=initial_capital,
                    market_type=market_type,
                    market_category=market_category,
                    margin_mode="cross",
                    stop_loss_price=None,
                    take_profit_price=None,
                    execution_mode=execution_mode,
                    notification_config=notification_config,
                    trading_config=trading_config,
                    ai_model_config=ai_model_config,
                    signal_ts=current_time,
                )
                futures[future] = signal

            for future in as_completed(futures):
                signal = futures[future]
                try:
                    result = future.result(timeout=30)
                    if result:
                        logger.info(
                            "Successfully executed signal: %s %s",
                            signal["symbol"],
                            signal["type"],
                        )
                except Exception as e:
                    logger.error(
                        "Failed to execute signal %s %s: %s",
                        signal["symbol"],
                        signal["type"],
                        e,
                    )

    def _get_timeframe_seconds(self, timeframe: str) -> int:
        """将 timeframe 字符串（如 1H、1m）转为秒数"""
        from app.data_sources.base import TIMEFRAME_SECONDS
        tf = str(timeframe or "1H").strip()
        if tf not in TIMEFRAME_SECONDS:
            tf = tf.upper() if tf.islower() else tf.lower()
        return int(TIMEFRAME_SECONDS.get(tf, 3600))

    def _is_strategy_running(self, strategy_id: int) -> bool:
        """检查策略是否在运行"""
        status = self.data_handler.get_strategy_status(strategy_id)
        return status == "running"

    def _fetch_current_price(
        self,
        exchange: Any,
        symbol: str,
        market_type: str = None,
        market_category: str = 'Crypto',
    ) -> Optional[float]:
        """获取当前价格 (根据 market_category 选择正确的数据源)

        Args:
            exchange: 交易所实例（信号模式下为 None）
            symbol: 交易对/代码
            market_type: 交易类型 (swap/spot)
            market_category: 市场类型 (Crypto, USStock, Forex, Futures, AShare, HShare)
        """
        # Local in-memory cache first
        cache_key = f"{market_category}:{(symbol or '').strip().upper()}"
        if cache_key and self._price_cache_ttl_sec > 0:
            now = time.time()
            try:
                with self._price_cache_lock:
                    item = self._price_cache.get(cache_key)
                    if item:
                        price, expiry = item
                        if expiry > now:
                            return float(price)
                        # expired
                        del self._price_cache[cache_key]
            except Exception:
                pass

        try:
            # 根据 market_category 选择正确的数据源
            # 支持: Crypto, USStock, Forex, Futures, AShare, HShare
            ticker = DataSourceFactory.get_ticker(market_category, symbol)
            if ticker:
                price = float(ticker.get('last') or ticker.get('close') or 0)
                if price > 0:
                    if cache_key and self._price_cache_ttl_sec > 0:
                        try:
                            with self._price_cache_lock:
                                self._price_cache[cache_key] = (float(price), time.time() + self._price_cache_ttl_sec)
                        except Exception:
                            pass
                    return price
        except Exception as e:
            logger.warning(
                "Failed to fetch price for %s:%s: %s",
                market_category,
                symbol,
                e,
            )

        return None

    def _server_side_stop_loss_signal(
        self,
        strategy_id: int,
        symbol: str,
        current_price: float,
        market_type: str,
        leverage: float,
        trading_config: Dict[str, Any],
        timeframe_seconds: int,
    ) -> Optional[Dict[str, Any]]:
        """
        服务端兜底止损：当价格穿透止损线时，直接生成 close_long/close_short 信号。

        目的：防止“指标回放逻辑导致最后一根K线没有 close_* 信号”或“插针反弹导致二次触发条件不满足”时不止损。
        """
        try:
            if trading_config is None:
                return None

            enabled = trading_config.get('enable_server_side_stop_loss', True)
            if str(enabled).lower() in ['0', 'false', 'no', 'off']:
                return None

            # 获取当前持仓（使用本地数据库记录作为风控依据）
            current_positions = self.data_handler.get_current_positions(strategy_id, symbol)
            if not current_positions:
                return None

            pos = current_positions[0]
            side = pos.get('side')
            if side not in ['long', 'short']:
                return None

            entry_price = float(pos.get('entry_price', 0) or 0)
            if entry_price <= 0 or current_price <= 0:
                return None

            # Stop-loss is config-driven: if stop_loss_pct is not set or <= 0, do NOT stop-loss.
            sl_cfg = trading_config.get('stop_loss_pct', 0)
            sl = 0.0
            try:
                sl_cfg = float(sl_cfg or 0)
                if sl_cfg > 1:
                    sl = sl_cfg / 100.0
                else:
                    sl = sl_cfg
            except Exception:
                sl = 0.0

            if sl <= 0:
                return None

            # Align with backtest semantics: risk percentages are defined on margin PnL,
            # so we convert to price move threshold by dividing by leverage.
            lev = max(1.0, float(leverage or 1.0))
            sl = sl / lev

            # Use candle start timestamp to deduplicate exit attempts within a candle.
            now_ts = int(time.time())
            tf = int(timeframe_seconds or 60)
            candle_ts = int(now_ts // tf) * tf

            # 多头：跌破止损线
            if side == 'long':
                stop_line = entry_price * (1 - sl)
                if current_price <= stop_line:
                    return {
                        'type': 'close_long',
                        'trigger_price': 0,  # 立即触发（由 exit_trigger_mode 控制）
                        'position_size': 0,
                        'timestamp': candle_ts,
                        'reason': 'server_stop_loss',
                        'stop_loss_price': stop_line,
                    }
            # 空头：突破止损线
            elif side == 'short':
                stop_line = entry_price * (1 + sl)
                if current_price >= stop_line:
                    return {
                        'type': 'close_short',
                        'trigger_price': 0,
                        'position_size': 0,
                        'timestamp': candle_ts,
                        'reason': 'server_stop_loss',
                        'stop_loss_price': stop_line,
                    }

            return None
        except Exception as e:
            logger.warning(
                "Strategy %s server-side stop-loss check failed: %s",
                strategy_id,
                e,
            )
            return None

    def _server_side_take_profit_or_trailing_signal(
        self,
        strategy_id: int,
        symbol: str,
        current_price: float,
        market_type: str,
        leverage: float,
        trading_config: Dict[str, Any],
        timeframe_seconds: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Server-side exits driven by trading_config (no indicator script required):
        - Fixed take-profit: take_profit_pct
        - Trailing stop: trailing_enabled + trailing_stop_pct + trailing_activation_pct

        Semantics align with BacktestService:
        - Percentages are defined on margin PnL; effective price threshold = pct / leverage.
        - When trailing is enabled, fixed take-profit is disabled to avoid ambiguity.
        """
        try:
            if not trading_config:
                return None

            current_positions = self.data_handler.get_current_positions(strategy_id, symbol)
            if not current_positions:
                return None

            pos = current_positions[0]
            side = (pos.get('side') or '').strip().lower()
            if side not in ['long', 'short']:
                return None

            entry_price = float(pos.get('entry_price', 0) or 0)
            if entry_price <= 0 or current_price <= 0:
                return None

            lev = max(1.0, float(leverage or 1.0))

            tp = self._to_ratio(trading_config.get('take_profit_pct'))
            trailing_enabled = bool(trading_config.get('trailing_enabled'))
            trailing_pct = self._to_ratio(trading_config.get('trailing_stop_pct'))
            trailing_act = self._to_ratio(trading_config.get('trailing_activation_pct'))

            tp_eff = (tp / lev) if tp > 0 else 0.0
            trailing_pct_eff = (trailing_pct / lev) if trailing_pct > 0 else 0.0
            trailing_act_eff = (trailing_act / lev) if trailing_act > 0 else 0.0

            # Conflict rule: when trailing is enabled, fixed TP is disabled.
            if trailing_enabled and trailing_pct_eff > 0:
                tp_eff = 0.0
                # If activationPct is missing, reuse take_profit_pct as activation threshold.
                if trailing_act_eff <= 0 and tp > 0:
                    trailing_act_eff = tp / lev

            now_ts = int(time.time())
            tf = int(timeframe_seconds or 60)
            candle_ts = int(now_ts // tf) * tf

            # Highest/lowest tracking (persisted in DB so restart continues trailing correctly)
            try:
                hp = float(pos.get('highest_price') or 0.0)
            except Exception:
                hp = 0.0
            try:
                lp = float(pos.get('lowest_price') or 0.0)
            except Exception:
                lp = 0.0

            if hp <= 0:
                hp = entry_price
            hp = max(hp, float(current_price))

            if lp <= 0:
                lp = entry_price
            lp = min(lp, float(current_price))

            # Persist best-effort
            try:
                self.data_handler.update_position(
                    strategy_id=strategy_id,
                    symbol=pos.get('symbol') or symbol,
                    side=side,
                    size=float(pos.get('size') or 0.0),
                    entry_price=entry_price,
                    current_price=float(current_price),
                    highest_price=hp,
                    lowest_price=lp,
                )
            except Exception:
                pass

            # 1) Trailing stop
            if trailing_enabled and trailing_pct_eff > 0:
                if side == 'long':
                    active = True
                    if trailing_act_eff > 0:
                        active = hp >= entry_price * (1 + trailing_act_eff)
                    if active:
                        stop_line = hp * (1 - trailing_pct_eff)
                        if current_price <= stop_line:
                            return {
                                'type': 'close_long',
                                'trigger_price': 0,
                                'position_size': 0,
                                'timestamp': candle_ts,
                                'reason': 'server_trailing_stop',
                                'trailing_stop_price': stop_line,
                                'highest_price': hp,
                            }
                else:
                    active = True
                    if trailing_act_eff > 0:
                        active = lp <= entry_price * (1 - trailing_act_eff)
                    if active:
                        stop_line = lp * (1 + trailing_pct_eff)
                        if current_price >= stop_line:
                            return {
                                'type': 'close_short',
                                'trigger_price': 0,
                                'position_size': 0,
                                'timestamp': candle_ts,
                                'reason': 'server_trailing_stop',
                                'trailing_stop_price': stop_line,
                                'lowest_price': lp,
                            }

            # 2) Fixed take-profit (only when trailing is disabled)
            if tp_eff > 0:
                if side == 'long':
                    tp_line = entry_price * (1 + tp_eff)
                    if current_price >= tp_line:
                        return {
                            'type': 'close_long',
                            'trigger_price': 0,
                            'position_size': 0,
                            'timestamp': candle_ts,
                            'reason': 'server_take_profit',
                            'take_profit_price': tp_line,
                        }
                else:
                    tp_line = entry_price * (1 - tp_eff)
                    if current_price <= tp_line:
                        return {
                            'type': 'close_short',
                            'trigger_price': 0,
                            'position_size': 0,
                            'timestamp': candle_ts,
                            'reason': 'server_take_profit',
                            'take_profit_price': tp_line,
                        }

            return None
        except Exception:
            return None

    def _process_and_execute_signals(
        self,
        strategy_id: int,
        symbol: str,
        triggered_signals: List[Dict[str, Any]],
        current_price: float,
        strategy_name: str,
        exchange: Any,
        trade_direction: str,
        leverage: float,
        initial_capital: float,
        market_type: str,
        market_category: str,
        execution_mode: str,
        notification_config: Optional[Dict[str, Any]],
        trading_config: Dict[str, Any],
        ai_model_config: Optional[Dict[str, Any]],
        timeframe_seconds: int,
    ) -> None:
        """
        信号执行：由 Executor 负责。策略仅生成 triggered_signals，本方法负责：
        - 添加服务端风控信号（止盈/止损/追踪止盈）
        - 过滤、排序、选择、执行
        """
        if not triggered_signals:
            return
        all_signals = list(triggered_signals)
        risk_tp = self._server_side_take_profit_or_trailing_signal(
            strategy_id=strategy_id, symbol=symbol, current_price=float(current_price),
            market_type=market_type, leverage=float(leverage), trading_config=trading_config,
            timeframe_seconds=int(timeframe_seconds or 60),
        )
        if risk_tp:
            all_signals.append(risk_tp)
        risk_sl = self._server_side_stop_loss_signal(
            strategy_id=strategy_id, symbol=symbol, current_price=float(current_price),
            market_type=market_type, leverage=float(leverage), trading_config=trading_config,
            timeframe_seconds=int(timeframe_seconds or 60),
        )
        if risk_sl:
            all_signals.append(risk_sl)

        current_positions = self.data_handler.get_current_positions(strategy_id, symbol)
        state = self._position_state(current_positions)
        candidates = [
            s for s in all_signals
            if self._is_signal_allowed(state, s.get("type"))
        ]
        if state == "flat" and candidates:
            td = (trade_direction or "both").strip().lower()
            if td == "long":
                candidates = [s for s in candidates if s.get("type") == "open_long"]
            elif td == "short":
                candidates = [s for s in candidates if s.get("type") == "open_short"]
        candidates = sorted(
            candidates,
            key=lambda s: (
                self._signal_priority(s.get("type")),
                int(s.get("timestamp") or 0),
                str(s.get("type") or ""),
            ),
        )
        selected = None
        now_i = int(time.time())
        for s in candidates:
            stype = s.get("type")
            sts = int(s.get("timestamp") or 0)
            if self._should_skip_signal_once_per_candle(
                strategy_id=strategy_id, symbol=symbol, signal_type=str(stype or ""),
                signal_ts=sts, timeframe_seconds=int(timeframe_seconds or 60), now_ts=now_i,
            ):
                continue
            selected = s
            break
        if selected:
            sig_type = selected.get("type")
            position_size = selected.get("position_size", 0)
            trigger_price = selected.get("trigger_price", current_price)
            execute_price = trigger_price if trigger_price > 0 else current_price
            signal_ts = int(selected.get("timestamp") or 0)
            ok = self._execute_signal(
                strategy_id=strategy_id, strategy_name=strategy_name, exchange=exchange,
                symbol=symbol, current_price=execute_price, signal_type=sig_type,
                position_size=position_size, signal_ts=signal_ts,
                current_positions=current_positions, trade_direction=trade_direction,
                leverage=leverage, initial_capital=initial_capital, market_type=market_type,
                market_category=market_category, execution_mode=execution_mode,
                notification_config=notification_config, trading_config=trading_config,
                ai_model_config=ai_model_config,
            )
            if ok:
                logger.info(
                    "Strategy %s signal executed: %s @ %s",
                    strategy_id, sig_type, execute_price,
                )
                try:
                    from app.services.portfolio_monitor import notify_strategy_signal_for_positions
                    notify_strategy_signal_for_positions(
                        market=market_type or "Crypto", symbol=symbol, signal_type=sig_type,
                        signal_detail=f"策略: {strategy_name}\n信号: {sig_type}\n价格: {execute_price:.4f}",
                    )
                except Exception as link_e:
                    logger.warning(
                        "Strategy signal linkage notification failed: %s",
                        link_e,
                    )
            else:
                logger.warning(
                    "Strategy %s signal rejected/failed: %s",
                    strategy_id, sig_type,
                )

    def _execute_signal(
        self,
        strategy_id: int,
        strategy_name: str,
        exchange: Any,
        symbol: str,
        current_price: float,
        signal_type: str,
        position_size: float,
        current_positions: List[Dict[str, Any]],
        trade_direction: str,
        leverage: int,
        initial_capital: float,
        market_type: str = 'swap',
        market_category: str = 'Crypto',
        margin_mode: str = 'cross',
        stop_loss_price: float = None,
        take_profit_price: float = None,
        execution_mode: str = 'signal',
        notification_config: Optional[Dict[str, Any]] = None,
        trading_config: Optional[Dict[str, Any]] = None,
        ai_model_config: Optional[Dict[str, Any]] = None,
        signal_ts: int = 0,
    ):
        """执行具体的交易信号"""
        try:
            # Hard state-machine guard (double safety in addition to loop-level filtering).
            state = self._position_state(current_positions)
            if not self._is_signal_allowed(state, signal_type):
                return False

            # 1. 检查交易方向限制
            if market_type == 'spot' and 'short' in signal_type:
                return False

            sig = (signal_type or "").strip().lower()

            # 1.1 开仓 AI 过滤（仅 open_*）
            if sig in ("open_long", "open_short") and self._is_entry_ai_filter_enabled(ai_model_config=ai_model_config, trading_config=trading_config):
                ok_ai, ai_info = self._entry_ai_filter_allows(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    signal_type=sig,
                    ai_model_config=ai_model_config,
                    trading_config=trading_config,
                )
                if not ok_ai:
                    # Best-effort persist a browser notification so UI can show "HOLD due to AI filter".
                    reason = (ai_info or {}).get("reason") or "ai_filter_rejected"
                    ai_decision = (ai_info or {}).get("ai_decision") or ""
                    title = f"AI过滤拦截开仓 | {symbol}"
                    msg = f"策略信号={sig}，AI决策={ai_decision or 'UNKNOWN'}，原因={reason}；已HOLD（不下单）"
                    self.data_handler.persist_notification(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        signal_type="ai_filter_hold",
                        title=title,
                        message=msg,
                        payload={
                            "event": "qd.ai_filter",
                            "strategy_id": int(strategy_id),
                            "strategy_name": str(strategy_name or ""),
                            "symbol": str(symbol or ""),
                            "signal_type": str(sig),
                            "ai_decision": str(ai_decision),
                            "reason": str(reason),
                            "signal_ts": int(signal_ts or 0),
                        },
                    )
                    logger.info(
                        "AI entry filter rejected: strategy_id=%s symbol=%s signal=%s ai=%s reason=%s",
                        strategy_id,
                        symbol,
                        sig,
                        ai_decision,
                        reason,
                    )
                    return False

            # 2. 计算下单数量
            available_capital = self._get_available_capital(strategy_id, initial_capital)

            amount = 0.0

            # Frontend position sizing alignment:
            # - open_* uses entry_pct from trading_config if provided (0~1 or 0~100 are both accepted)
            if sig in ("open_long", "open_short") and isinstance(trading_config, dict):
                ep = trading_config.get("entry_pct")
                if ep is not None:
                    position_size = self._to_ratio(ep, default=position_size if position_size is not None else 0.0)

            # Open / add sizing: position_size is treated as capital ratio in [0,1].
            if ('open' in sig or 'add' in sig):
                if position_size is None or float(position_size) <= 0:
                    position_size = 0.05
                position_ratio = self._to_ratio(position_size, default=0.05)
                if market_type == 'spot':
                    amount = available_capital * position_ratio / current_price
                else:
                    # Futures sizing: treat available_capital as margin budget.
                    # Notional = margin * leverage, so base quantity = (margin * leverage) / price.
                    amount = (available_capital * position_ratio * leverage) / current_price

            # Reduce sizing: position_size is treated as a reduce ratio (close X% of current position).
            if sig in ("reduce_long", "reduce_short"):
                pos_side = "long" if "long" in sig else "short"
                pos = next((p for p in current_positions if (p.get('side') or '').strip().lower() == pos_side), None)
                if not pos:
                    return False
                cur_size = float(pos.get("size") or 0.0)
                if cur_size <= 0:
                    return False
                reduce_ratio = self._to_ratio(position_size, default=0.1)
                reduce_amount = cur_size * reduce_ratio
                # If reduce is effectively full, treat as close_*.
                if reduce_amount >= cur_size * 0.999:
                    sig = "close_long" if pos_side == "long" else "close_short"
                    signal_type = sig
                    amount = cur_size
                else:
                    amount = reduce_amount

            # 3. 检查反向持仓（单向持仓逻辑）
            # ... (简化处理，假设无反向或由用户处理) ...

            # 4. Execute order enqueue (PendingOrderWorker will dispatch notifications in signal mode)
            if 'close' in sig:
                # 平仓逻辑：找到对应持仓大小
                pos = next((p for p in current_positions if p.get('side') and p['side'] in signal_type), None)
                if not pos:
                    return False
                amount = float(pos['size'] or 0.0)
                if amount <= 0:
                    return False

            if amount <= 0 and ('open' in signal_type or 'add' in signal_type):
                return False

            order_result = self._execute_exchange_order(
                exchange=exchange,
                strategy_id=strategy_id,
                symbol=symbol,
                signal_type=signal_type,
                amount=amount,
                ref_price=float(current_price or 0.0),
                market_type=market_type,
                market_category=market_category,
                leverage=leverage,
                execution_mode=execution_mode,
                notification_config=notification_config,
                signal_ts=int(signal_ts or 0),
            )

            if order_result and order_result.get('success'):
                # For live execution, the order is only enqueued here.
                # The actual fill/trade/position updates are performed by PendingOrderWorker.
                if str(execution_mode or "").strip().lower() == "live":
                    return True

                # 更新数据库状态 (signal mode / local simulation)
                if 'open' in sig or 'add' in sig:
                    self.data_handler.record_trade(
                        strategy_id=strategy_id, symbol=symbol, trade_type=signal_type,
                        price=current_price, amount=amount, value=amount*current_price
                    )
                    side = 'short' if 'short' in signal_type else 'long'

                    # 查找现有持仓以计算均价
                    old_pos = next((p for p in current_positions if p['side'] == side), None)
                    new_size = amount
                    new_entry = current_price
                    if old_pos:
                        old_size = float(old_pos['size'])
                        old_entry = float(old_pos['entry_price'])
                        new_size += old_size
                        new_entry = ((old_size * old_entry) + (amount * current_price)) / new_size

                    self.data_handler.update_position(
                        strategy_id=strategy_id, symbol=symbol, side=side,
                        size=new_size, entry_price=new_entry, current_price=current_price
                    )
                elif sig.startswith("reduce_"):
                    # Partial scale-out: reduce position size, keep entry price unchanged.
                    # 信号模式下计算部分平仓盈亏
                    side = 'short' if 'short' in signal_type else 'long'
                    old_pos = next((p for p in current_positions if p.get('side') == side), None)
                    if not old_pos:
                        return True
                    old_size = float(old_pos.get('size') or 0.0)
                    old_entry = float(old_pos.get('entry_price') or 0.0)

                    # 计算减仓部分的盈亏（信号模式下，不含手续费）
                    reduce_profit = None
                    if old_entry > 0 and amount > 0:
                        if side == 'long':
                            reduce_profit = (current_price - old_entry) * amount
                        else:
                            reduce_profit = (old_entry - current_price) * amount

                    self.data_handler.record_trade(
                        strategy_id=strategy_id, symbol=symbol, trade_type=signal_type,
                        price=current_price, amount=amount, value=amount*current_price,
                        profit=reduce_profit
                    )

                    new_size = max(0.0, old_size - float(amount or 0.0))
                    if new_size <= old_size * 0.001:
                        self.data_handler.close_position(strategy_id, symbol, side)
                    else:
                        self.data_handler.update_position(
                            strategy_id=strategy_id, symbol=symbol, side=side,
                            size=new_size, entry_price=old_entry, current_price=current_price
                        )
                elif 'close' in sig:
                    # 信号模式下计算平仓盈亏
                    side = 'short' if 'short' in signal_type else 'long'
                    old_pos = next((p for p in current_positions if p.get('side') == side), None)

                    # 计算盈亏（信号模式下，不含手续费）
                    close_profit = None
                    if old_pos:
                        entry_price = float(old_pos.get('entry_price') or 0)
                        if entry_price > 0 and amount > 0:
                            if side == 'long':
                                close_profit = (current_price - entry_price) * amount
                            else:
                                close_profit = (entry_price - current_price) * amount

                    self.data_handler.record_trade(
                        strategy_id=strategy_id, symbol=symbol, trade_type=signal_type,
                        price=current_price, amount=amount, value=amount*current_price,
                        profit=close_profit
                    )
                    self.data_handler.close_position(strategy_id, symbol, side)

                return True

            return False

        except Exception as e:
            logger.error("Failed to execute signal: %s", e)
            return False

    def _is_entry_ai_filter_enabled(self, *, ai_model_config: Optional[Dict[str, Any]], trading_config: Optional[Dict[str, Any]]) -> bool:
        """Detect whether the strategy enabled 'AI filter on entry (open positions only)'."""
        amc = ai_model_config if isinstance(ai_model_config, dict) else {}
        tc = trading_config if isinstance(trading_config, dict) else {}

        # Accept multiple key names for forward/backward compatibility.
        candidates = [
            amc.get("entry_ai_filter_enabled"),
            amc.get("entryAiFilterEnabled"),
            amc.get("ai_filter_enabled"),
            amc.get("aiFilterEnabled"),
            amc.get("enable_ai_filter"),
            amc.get("enableAiFilter"),
            tc.get("entry_ai_filter_enabled"),
            tc.get("ai_filter_enabled"),
            tc.get("enable_ai_filter"),
            tc.get("enableAiFilter"),
        ]
        for v in candidates:
            if v is None:
                continue
            if isinstance(v, bool):
                return bool(v)
            s = str(v).strip().lower()
            if s in ("1", "true", "yes", "y", "on", "enabled"):
                return True
            if s in ("0", "false", "no", "n", "off", "disabled"):
                return False
        return False

    def _entry_ai_filter_allows(
        self,
        *,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        ai_model_config: Optional[Dict[str, Any]],
        trading_config: Optional[Dict[str, Any]],
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Run internal AI analysis and decide whether an entry signal is allowed.

        Returns:
          (allowed, info)
          - allowed: True -> proceed; False -> hold (reject open)
          - info: {ai_decision, reason, analysis_error?}
        """
        amc = ai_model_config if isinstance(ai_model_config, dict) else {}
        tc = trading_config if isinstance(trading_config, dict) else {}

        # Market for AnalysisService. Live trading executor is Crypto-focused.
        market = str(amc.get("market") or amc.get("analysis_market") or "Crypto").strip() or "Crypto"

        # Optional model override (OpenRouter model id)
        model = amc.get("model") or amc.get("openrouter_model") or amc.get("openrouterModel") or None
        model = str(model).strip() if model else None

        # Prefer zh-CN for local UI; can be overridden.
        language = amc.get("language") or amc.get("lang") or tc.get("language") or "zh-CN"
        language = str(language or "zh-CN")

        try:
            # 使用新的 FastAnalysisService (单次LLM调用，更快更稳定)
            from app.services.fast_analysis import get_fast_analysis_service

            service = get_fast_analysis_service()
            result = service.analyze(market, symbol, language, model=model)

            if isinstance(result, dict) and result.get("error"):
                return False, {"ai_decision": "", "reason": "analysis_error", "analysis_error": str(result.get("error") or "")}

            # FastAnalysisService 直接返回 decision 字段
            ai_dec = str(result.get("decision", "")).strip().upper()
            if not ai_dec or ai_dec not in ("BUY", "SELL", "HOLD"):
                return False, {"ai_decision": ai_dec, "reason": "missing_ai_decision"}

            expected = "BUY" if signal_type == "open_long" else "SELL"
            confidence = result.get("confidence", 50)
            summary = result.get("summary", "")

            if ai_dec == expected:
                return True, {"ai_decision": ai_dec, "reason": "match", "confidence": confidence, "summary": summary}
            if ai_dec == "HOLD":
                return False, {"ai_decision": ai_dec, "reason": "ai_hold", "confidence": confidence, "summary": summary}
            return False, {"ai_decision": ai_dec, "reason": "direction_mismatch", "confidence": confidence, "summary": summary}
        except Exception as e:
            return False, {"ai_decision": "", "reason": "analysis_exception", "analysis_error": str(e)}

    def _extract_ai_trade_decision(self, analysis_result: Any) -> str:
        """
        Normalize AI analysis output into one of: BUY / SELL / HOLD / "".
        We primarily look at final_decision.decision, with fallbacks.
        """
        if not isinstance(analysis_result, dict):
            return ""

        def _pick(*paths: str) -> str:
            for p in paths:
                cur: Any = analysis_result
                ok = True
                for k in p.split("."):
                    if not isinstance(cur, dict):
                        ok = False
                        break
                    cur = cur.get(k)
                if ok and cur is not None:
                    s = str(cur).strip()
                    if s:
                        return s
            return ""

        raw = _pick("final_decision.decision", "trader_decision.decision", "decision", "final.decision")
        s = raw.strip().upper()
        if not s:
            return ""

        # Common variants / synonyms
        if "BUY" in s or s == "LONG" or "LONG" in s:
            return "BUY"
        if "SELL" in s or s == "SHORT" or "SHORT" in s:
            return "SELL"
        if "HOLD" in s or "WAIT" in s or "NEUTRAL" in s:
            return "HOLD"
        return s if s in ("BUY", "SELL", "HOLD") else ""

    def _execute_exchange_order(
        self,
        exchange: Any,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        amount: float,
        ref_price: Optional[float] = None,
        market_type: str = 'swap',
        market_category: str = 'Crypto',
        leverage: float = 1.0,
        margin_mode: str = 'cross',
        stop_loss_price: float = None,
        take_profit_price: float = None,
        # Order execution params (order_mode, maker_wait_sec, maker_offset_bps) are now
        # configured via environment variables: ORDER_MODE, MAKER_WAIT_SEC, MAKER_OFFSET_BPS
        # These parameters are kept for backward compatibility but will be ignored.
        order_mode: str = None,
        maker_wait_sec: float = None,
        maker_retries: int = 3,
        close_fallback_to_market: bool = True,
        open_fallback_to_market: bool = True,
        execution_mode: str = 'signal',
        notification_config: Optional[Dict[str, Any]] = None,
        signal_ts: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """
        Convert a signal into a concrete pending order and enqueue it into DB.

        A separate worker will poll `pending_orders` and dispatch:
        - execution_mode='signal': dispatch notifications (no real trading).
        - execution_mode='live': reserved for future live trading execution (not implemented).

        Note: Order execution settings (order_mode, maker_wait_sec, maker_offset_bps) are now
        configured via environment variables and not passed from strategy config.
        """
        try:
            # Reference price at enqueue time: use current tick price if provided to avoid extra fetch.
            if ref_price is None:
                ref_price = self._fetch_current_price(None, symbol, market_category=market_category) or 0.0
            ref_price = float(ref_price or 0.0)

            extra_payload = {
                "ref_price": float(ref_price or 0.0),
                "signal_ts": int(signal_ts or 0),
                "stop_loss_price": float(stop_loss_price or 0.0) if stop_loss_price is not None else 0.0,
                "take_profit_price": float(take_profit_price or 0.0) if take_profit_price is not None else 0.0,
                "margin_mode": str(margin_mode or "cross"),
                # Order execution params moved to env config (ORDER_MODE, MAKER_WAIT_SEC, MAKER_OFFSET_BPS)
                "maker_retries": int(maker_retries or 0),
                "close_fallback_to_market": bool(close_fallback_to_market),
                "open_fallback_to_market": bool(open_fallback_to_market),
            }
            pending_id = self._enqueue_pending_order(
                strategy_id=strategy_id,
                symbol=symbol,
                signal_type=signal_type,
                amount=float(amount or 0.0),
                price=float(ref_price or 0.0),
                signal_ts=int(signal_ts or 0),
                market_type=market_type,
                leverage=float(leverage or 1.0),
                execution_mode=execution_mode,
                notification_config=notification_config,
                extra_payload=extra_payload,
            )

            pending_flag = str(execution_mode or "").strip().lower() == "live"

            # Local "signal provider mode": we keep the local state machine moving forward.
            return {
                'success': True,
                'pending': bool(pending_flag),
                'order_id': f"pending_{pending_id or int(time.time()*1000)}",
                'filled_amount': 0 if pending_flag else amount,
                'filled_base_amount': 0 if pending_flag else amount,
                'filled_price': 0 if pending_flag else ref_price,
                'total_cost': 0 if pending_flag else (float(amount or 0.0) * float(ref_price or 0.0) if ref_price else 0),
                'fee': 0,
                'message': 'Order enqueued to pending_orders'
            }
        except Exception as e:
            logger.error("Signal execution failed: %s", e)
            return {'success': False, 'error': str(e)}

    def _enqueue_pending_order(
        self,
        strategy_id: int,
        symbol: str,
        signal_type: str,
        amount: float,
        price: float,
        signal_ts: int,
        market_type: str,
        leverage: float,
        execution_mode: str,
        notification_config: Optional[Dict[str, Any]] = None,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Insert a pending order record and return its id."""
        try:
            now = int(time.time())
            # Local deployment supports both "signal" and "live" (live is executed by PendingOrderWorker).
            mode = (execution_mode or "signal").strip().lower()
            if mode not in ("signal", "live"):
                mode = "signal"

            payload: Dict[str, Any] = {
                "strategy_id": int(strategy_id),
                "symbol": symbol,
                "signal_type": signal_type,
                "market_type": market_type,
                "amount": float(amount or 0.0),
                "price": float(price or 0.0),
                "leverage": float(leverage or 1.0),
                "execution_mode": mode,
                "notification_config": notification_config or {},
                "signal_ts": int(signal_ts or 0),
            }
            if extra_payload and isinstance(extra_payload, dict):
                payload.update(extra_payload)

            stsig = int(signal_ts or 0)
            sig_norm = str(signal_type or "").strip().lower()
            strict_candle_dedup = stsig > 0 and sig_norm in ("open_long", "open_short", "close_long", "close_short")

            last = self.data_handler.find_recent_pending_order(
                strategy_id, symbol, signal_type, stsig if strict_candle_dedup else None
            )
            last_id = int((last or {}).get("id") or 0)
            last_status = str((last or {}).get("status") or "").strip().lower()
            last_created = int((last or {}).get("created_at") or 0)
            cooldown_sec = 30

            if last_id > 0:
                if strict_candle_dedup:
                    logger.info(
                        "enqueue_pending_order skipped (same candle): existing id=%s strategy_id=%s symbol=%s signal=%s signal_ts=%s status=%s",
                        last_id, strategy_id, symbol, signal_type, stsig, last_status,
                    )
                    return None
                if last_status in ("pending", "processing"):
                    logger.info(
                        "enqueue_pending_order skipped: existing_inflight id=%s strategy_id=%s symbol=%s signal=%s status=%s",
                        last_id, strategy_id, symbol, signal_type, last_status,
                    )
                    return None
                if last_created > 0 and (now - last_created) < cooldown_sec:
                    logger.info(
                        "enqueue_pending_order cooldown: last_id=%s last_status=%s age_sec=%s (<%s) strategy_id=%s symbol=%s signal=%s",
                        last_id, last_status, now - last_created, cooldown_sec, strategy_id, symbol, signal_type,
                    )
                    return None

            user_id = self.data_handler.get_user_id(strategy_id)
            pending_id = self.data_handler.insert_pending_order(
                user_id=user_id,
                strategy_id=strategy_id,
                symbol=symbol,
                signal_type=signal_type,
                signal_ts=stsig,
                market_type=market_type or "swap",
                order_type="market",
                amount=float(amount or 0.0),
                price=float(price or 0.0),
                execution_mode=mode,
                status="pending",
                priority=0,
                attempts=0,
                max_attempts=10,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
            return int(pending_id) if pending_id is not None else None
        except Exception as e:
            logger.error("enqueue_pending_order failed: %s", e)
            return None

    def _get_available_capital(self, strategy_id: int, initial_capital: float) -> float:
        """获取可用资金：优先从 PortfolioAllocator 获取动态分配，fallback 到 initial_capital。"""
        try:
            from app.services.portfolio_allocator import get_portfolio_allocator
            allocator = get_portfolio_allocator()
            allocated = allocator.get_allocated_capital(strategy_id)
            if allocated is not None:
                return allocated
        except Exception:
            pass
        return initial_capital

    def _should_rebalance(self, strategy_id: int, rebalance_frequency: str) -> bool:
        """检查是否应该调仓（执行调度逻辑）。数据由 DataHandler 提供。"""
        last_rebalance = self.data_handler.get_last_rebalance_at(strategy_id)
        if last_rebalance is None:
            return True
        delta = datetime.now() - last_rebalance
        if rebalance_frequency == "daily":
            return delta.days >= 1
        if rebalance_frequency == "weekly":
            return delta.days >= 7
        if rebalance_frequency == "monthly":
            return delta.days >= 30
        return True
