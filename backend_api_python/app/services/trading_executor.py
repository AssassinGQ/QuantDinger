"""
实时交易执行服务
"""
import threading
import traceback
import os
from typing import Any
try:
    import psutil
except ImportError:
    psutil = None

from app.utils.logger import get_logger
from app.strategies.factory import load_and_create
from app.services.data_handler import DataHandler
from app.services.signal_executor import SignalExecutor
from app.services.price_fetcher import get_price_fetcher
from app.utils.console import console_print
from app.strategies.runners.factory import create_runner

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
            except (KeyError, ValueError, AttributeError):
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
        except (KeyError, ValueError, AttributeError, TypeError):
            return symbol

    def _log_resource_status(self, prefix: str = ""):
        """调试：记录线程/内存使用，便于定位 can't start new thread 根因"""
        if psutil:
            try:
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
                return
            except (OSError, RuntimeError, AttributeError):
                pass

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
            except OSError:
                pass
            vmrss_str = f"{vmrss[0]}{vmrss[1]}" if vmrss else "N/A"
            logger.warning(
                "%sresource status: VmRSS=%s, active_threads=%s, running_strategies=%d",
                prefix,
                vmrss_str,
                th,
                len(self.running_strategies),
            )
        except (RuntimeError, OSError):
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
                except RuntimeError as e:
                    # 捕获 can't start new thread 等异常，记录资源状态
                    self._log_resource_status(prefix="启动异常")
                    raise e
                self.running_strategies[strategy_id] = thread

                logger.info("Strategy %s started", strategy_id)
                console_print(f"[strategy:{strategy_id}] started")
                return True

        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as e:
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

        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as e:
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

            runner = create_runner(
                cs_type=cs_type,
                data_handler=self.data_handler,
                signal_executor=self._signal_executor,
            )
            runner.run(
                strategy_id=strategy_id,
                strategy=strategy,
                strat_instance=strat,
                exchange=exchange,
            )
        except (ValueError, TypeError, KeyError, RuntimeError, OSError, ImportError) as e:
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
