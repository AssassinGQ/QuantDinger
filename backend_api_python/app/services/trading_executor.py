"""
实时交易执行服务
"""
import time
import threading
import traceback
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
from app.utils.logger import get_logger
from app.strategies.factory import load_and_create
from app.strategies.base import sleep_until_next_tick
from app.services.data_handler import DataHandler
from app.services.signal_processor import process_signals
from app.services.signal_executor import SignalExecutor
from app.services.price_fetcher import get_price_fetcher
from app.utils.console import console_print

logger = get_logger(__name__)


class TradingExecutor:
    """实时交易执行器 (Signal Provider Mode)"""

    def __init__(self):
        # 不再使用全局连接，改为每次使用时从连接池获取
        self.running_strategies = {}  # {strategy_id: thread}
        self.lock = threading.Lock()
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
                    self._signal_executor.execute,
                    strategy_ctx=strategy,
                    signal=signal,
                    symbol=signal["symbol"],
                    current_price=0.0,
                    current_positions=symbol_positions,
                    exchange=None,
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
            
        selected, current_positions = process_signals(
            strategy_ctx=strategy,
            symbol=symbol,
            triggered_signals=triggered_signals,
            current_price=current_price,
        )
        if selected:
            sig_type = selected.get("type")
            trigger_price = selected.get("trigger_price", current_price)
            execute_price = trigger_price if trigger_price > 0 else current_price

            ok = self._signal_executor.execute(
                strategy_ctx=strategy,
                signal=selected,
                symbol=symbol,
                current_price=execute_price,
                current_positions=current_positions,
                exchange=exchange,
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
