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
from app.services.server_side_risk import to_ratio
from app.services.signal_processor import (
    is_signal_allowed,
    position_state,
    process_signals,
)
from app.services.signal_executor import SignalExecutor
from app.services.price_fetcher import get_price_fetcher
from app.data_sources import DataSourceFactory
from app.utils.console import console_print

logger = get_logger(__name__)


class TradingExecutor:
    """实时交易执行器 (Signal Provider Mode)"""

    def __init__(self):
        # 不再使用全局连接，改为每次使用时从连接池获取
        self.running_strategies = {}  # {strategy_id: thread}
        self.lock = threading.Lock()
        # In-memory signal de-dup cache to prevent repeated orders on the same candle signal.
        # Keyed by (strategy_id, symbol, signal_type, signal_timestamp).
        self._signal_dedup = {}  # type: Dict[int, Dict[str, float]]
        self._signal_dedup_lock = threading.Lock()
        self.data_handler = DataHandler()
        self._price_fetcher = get_price_fetcher()
        self._signal_executor = SignalExecutor()

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
                stale_ids = [
                    sid for sid, th in self.running_strategies.items()
                    if not th.is_alive()
                ]
                for sid in stale_ids:
                    del self.running_strategies[sid]

                if len(self.running_strategies) >= self.max_threads:
                    logger.error(
                        "Thread limit reached (running=%d, max=%d); refuse to start strategy %d. "
                        "Reduce running strategies or set STRATEGY_MAX_THREADS in .env",
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
                console_print(f"[strategy:{strategy_id}] started")
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
                console_print(f"[strategy:{strategy_id}] stopped (requested)")
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
        console_print(f"[strategy:{strategy_id}] loop initializing")

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
            console_print(f"[strategy:{strategy_id}] fatal error: {e}")
        finally:
            # 清理
            with self.lock:
                if strategy_id in self.running_strategies:
                    del self.running_strategies[strategy_id]
            console_print(f"[strategy:{strategy_id}] loop exited")
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
        tick_interval_sec = max(tick_interval_sec, 1)

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

                current_price = self._price_fetcher.fetch_current_price(
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
                        strategy=strategy,
                        symbol=symbol,
                        triggered_signals=triggered_signals,
                        current_price=float(current_price),
                        exchange=exchange,
                    )

                self.data_handler.update_positions_current_price(strategy_id, symbol, current_price)
                # SingleSymbolIndicator 内部 pending_signals，暂无公开 API，用于控制台输出
                pending_count = len(strat._state.get("pending_signals", []))
                price_str = f"{float(current_price or 0.0):.8f}"
                console_print(
                    f"[strategy:{strategy_id}] tick price={price_str} pending_signals={pending_count}"
                )
            except Exception as e:
                logger.error("Strategy %s loop error: %s", strategy_id, e)
                logger.error(traceback.format_exc())
                console_print(f"[strategy:{strategy_id}] loop error: {e}")
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
                reb_freq = request.get("rebalance_frequency", "daily")
                if not self._should_rebalance(strategy_id, reb_freq):
                    continue

                ctx = self.data_handler.get_input_context_cross(strategy_id, request)
                if ctx is None:
                    logger.warning(
                    "Strategy %s failed to get cross input context", strategy_id
                )
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
                console_print(f"[strategy:{strategy_id}] loop error: {e}")
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

        positions = self.data_handler.get_all_positions(strategy_id)

        with ThreadPoolExecutor(max_workers=min(10, len(signals))) as pool:
            futures = {}
            for signal in signals:
                sig_symbol = (signal.get("symbol") or "")
                symbol_positions = [
                    p for p in positions
                    if (p.get("symbol") or "").split(":")[0] == sig_symbol.split(":")[0]
                ]
                
                # Default timestamp if missing
                if not signal.get("timestamp"):
                    signal["timestamp"] = int(current_time)

                future = pool.submit(
                    self._execute_signal,
                    strategy_id=strategy_id,
                    strategy=strategy,
                    exchange=None,
                    symbol=signal["symbol"],
                    current_price=0.0,
                    signal=signal,
                    current_positions=symbol_positions,
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

    def _process_and_execute_signals(
        self,
        strategy_id: int,
        strategy: Dict[str, Any],
        symbol: str,
        triggered_signals: List[Dict[str, Any]],
        current_price: float,
        exchange: Any = None,
    ) -> None:
        """
        信号执行：由 Executor 负责。策略仅生成 triggered_signals，本方法负责：
        - 添加服务端风控信号（止盈/止损/追踪止盈）
        - 过滤、排序、选择、执行
        """
        if not triggered_signals:
            return
            
        leverage = float(strategy.get("_leverage", 1.0))
        market_type = strategy.get("_market_type", "swap")
        trading_config = strategy.get("trading_config") or {}
        trade_direction = "long" if market_type == "spot" else trading_config.get("trade_direction", "long")
        timeframe_seconds = self._get_timeframe_seconds(trading_config.get("timeframe", "1H"))

        selected, current_positions = process_signals(
            strategy_id=strategy_id,
            symbol=symbol,
            triggered_signals=triggered_signals,
            current_price=current_price,
            trade_direction=trade_direction,
            leverage=leverage,
            market_type=market_type,
            trading_config=trading_config,
            timeframe_seconds=timeframe_seconds,
            dedup_check=self._should_skip_signal_once_per_candle,
            now_ts=int(time.time()),
        )
        if selected:
            sig_type = selected.get("type")
            trigger_price = selected.get("trigger_price", current_price)
            execute_price = trigger_price if trigger_price > 0 else current_price

            ok = self._execute_signal(
                strategy_id=strategy_id,
                strategy=strategy,
                exchange=exchange,
                symbol=symbol,
                current_price=execute_price,
                signal=selected,
                current_positions=current_positions,
            )
            if ok:
                strategy_name = strategy.get("_strategy_name", "")
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
        strategy: Dict[str, Any],
        exchange: Any,
        symbol: str,
        current_price: float,
        signal: Dict[str, Any],
        current_positions: List[Dict[str, Any]],
    ):
        """执行具体的交易信号（保留 state machine、trade direction、AI filter；其余委托 signal_executor）"""
        try:
            signal_type = signal.get("type", "")
            
            # Hard state-machine guard (double safety in addition to loop-level filtering).
            state = position_state(current_positions)
            if not is_signal_allowed(state, signal_type):
                return False

            market_type = strategy.get("_market_type", "swap")
            # 1. 检查交易方向限制
            if market_type == 'spot' and 'short' in signal_type:
                return False

            sig = signal_type.strip().lower()

            ai_model_config = strategy.get("ai_model_config") or {}
            trading_config = strategy.get("trading_config") or {}

            # 1.1 开仓 AI 过滤（仅 open_*）
            ai_enabled = self._is_entry_ai_filter_enabled(
                ai_model_config=ai_model_config, trading_config=trading_config
            )
            if sig in ("open_long", "open_short") and ai_enabled:
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
                    msg = (
                        f"策略信号={sig}，AI决策={ai_decision or 'UNKNOWN'}，"
                        f"原因={reason}；已HOLD（不下单）"
                    )
                    self.data_handler.persist_notification(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        signal_type="ai_filter_hold",
                        title=title,
                        message=msg,
                        payload={
                            "event": "qd.ai_filter",
                            "strategy_id": int(strategy_id),
                            "strategy_name": str(strategy.get("_strategy_name", "")),
                            "symbol": str(symbol or ""),
                            "signal_type": str(sig),
                            "ai_decision": str(ai_decision),
                            "reason": str(reason),
                            "signal_ts": int(signal.get("timestamp") or 0),
                        },
                    )
                    logger.info(
                        "AI entry filter rejected: strategy_id=%s symbol=%s signal=%s ai=%s reason=%s",
                        strategy_id, symbol, sig, ai_decision, reason,
                    )
                    return False

            return self._signal_executor.execute(
                strategy_ctx=strategy,
                signal=signal,
                symbol=symbol,
                current_price=current_price,
                current_positions=current_positions,
                exchange=exchange,
            )
        except Exception as e:
            logger.error("Failed to execute signal: %s", e)
            return False

    def _is_entry_ai_filter_enabled(
        self,
        *,
        ai_model_config: Optional[Dict[str, Any]],
        trading_config: Optional[Dict[str, Any]],
    ) -> bool:
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
        market = str(
            amc.get("market") or amc.get("analysis_market") or "Crypto"
        ).strip() or "Crypto"

        # Optional model override (OpenRouter model id)
        model = (
            amc.get("model") or amc.get("openrouter_model")
            or amc.get("openrouterModel") or None
        )
        model = str(model).strip() if model else None

        # Prefer zh-CN for local UI; can be overridden.
        language = (
            amc.get("language") or amc.get("lang")
            or tc.get("language") or "zh-CN"
        )
        language = str(language or "zh-CN")

        try:
            # 使用新的 FastAnalysisService (单次LLM调用，更快更稳定)
            from app.services.fast_analysis import get_fast_analysis_service

            service = get_fast_analysis_service()
            result = service.analyze(market, symbol, language, model=model)

            if isinstance(result, dict) and result.get("error"):
                err_msg = str(result.get("error") or "")
                return False, {
                    "ai_decision": "",
                    "reason": "analysis_error",
                    "analysis_error": err_msg,
                }

            # FastAnalysisService 直接返回 decision 字段
            ai_dec = str(result.get("decision", "")).strip().upper()
            if not ai_dec or ai_dec not in ("BUY", "SELL", "HOLD"):
                return False, {"ai_decision": ai_dec, "reason": "missing_ai_decision"}

            expected = "BUY" if signal_type == "open_long" else "SELL"
            confidence = result.get("confidence", 50)
            summary = result.get("summary", "")

            info = {"ai_decision": ai_dec, "confidence": confidence, "summary": summary}
            if ai_dec == expected:
                return True, {**info, "reason": "match"}
            if ai_dec == "HOLD":
                return False, {**info, "reason": "ai_hold"}
            return False, {**info, "reason": "direction_mismatch"}
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
