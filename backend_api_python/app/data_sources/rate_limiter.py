# -*- coding: utf-8 -*-
"""
===================================
防封禁工具模块 (Rate Limiter)
===================================

参考 daily_stock_analysis 项目实现
提供反爬虫策略：
1. 随机休眠（Jitter）
2. 随机 User-Agent 轮换
3. 指数退避重试
4. 请求频率限制
"""

import time
import random
import logging
from typing import Optional, Callable, Any, Type, Tuple
from functools import wraps

logger = logging.getLogger(__name__)


# ============================================
# User-Agent 池
# ============================================

USER_AGENTS = [
    # Chrome Windows
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    # Chrome Mac
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    # Firefox
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    # Safari
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    # Edge
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
    # Linux Chrome
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]


def get_random_user_agent() -> str:
    """获取随机 User-Agent"""
    return random.choice(USER_AGENTS)


def get_request_headers(referer: Optional[str] = None) -> dict:
    """
    获取带有随机 User-Agent 的请求头
    
    Args:
        referer: 可选的 Referer 头
        
    Returns:
        请求头字典
    """
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    if referer:
        headers['Referer'] = referer
    
    return headers


# ============================================
# 随机休眠
# ============================================

def random_sleep(
    min_seconds: float = 1.0,
    max_seconds: float = 3.0,
    log: bool = False
) -> None:
    """
    随机休眠（Jitter）
    
    防封禁策略：模拟人类行为的随机延迟
    在请求之间加入不规则的等待时间
    
    Args:
        min_seconds: 最小休眠时间（秒）
        max_seconds: 最大休眠时间（秒）
        log: 是否记录日志
    """
    sleep_time = random.uniform(min_seconds, max_seconds)
    if log:
        logger.debug(f"随机休眠 {sleep_time:.2f} 秒...")
    time.sleep(sleep_time)


# ============================================
# 请求频率限制器
# ============================================

class RateLimiter:
    """
    请求频率限制器
    
    确保请求之间有最小间隔时间
    """
    
    def __init__(
        self,
        min_interval: float = 1.0,
        jitter_min: float = 0.5,
        jitter_max: float = 1.5
    ):
        """
        初始化频率限制器
        
        Args:
            min_interval: 最小请求间隔（秒）
            jitter_min: 随机抖动最小值（秒）
            jitter_max: 随机抖动最大值（秒）
        """
        self.min_interval = min_interval
        self.jitter_min = jitter_min
        self.jitter_max = jitter_max
        self._last_request_time: Optional[float] = None
    
    def wait(self) -> float:
        """
        等待直到可以发起下一次请求
        
        Returns:
            实际等待的时间（秒）
        """
        wait_time = 0.0
        
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.min_interval:
                # 补充休眠到最小间隔
                wait_time = self.min_interval - elapsed
                time.sleep(wait_time)
        
        # 添加随机抖动
        jitter = random.uniform(self.jitter_min, self.jitter_max)
        time.sleep(jitter)
        wait_time += jitter
        
        # 记录本次请求时间
        self._last_request_time = time.time()
        
        return wait_time
    
    def reset(self) -> None:
        """重置限制器"""
        self._last_request_time = None


# ============================================
# 指数退避重试装饰器
# ============================================

def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """
    指数退避重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        exponential_base: 指数基数
        exceptions: 需要重试的异常类型
        on_retry: 重试时的回调函数
        
    使用示例:
        @retry_with_backoff(max_attempts=3, exceptions=(ConnectionError, TimeoutError))
        def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.error(f"[重试] {func.__name__} 已达最大重试次数 ({max_attempts})，放弃")
                        raise
                    
                    # 计算退避延迟: base_delay * (exponential_base ^ (attempt - 1))
                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )
                    # 添加随机抖动 (±20%)
                    delay *= random.uniform(0.8, 1.2)
                    
                    logger.warning(
                        f"[重试] {func.__name__} 第 {attempt}/{max_attempts} 次失败: {e}, "
                        f"等待 {delay:.1f}s 后重试..."
                    )
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    time.sleep(delay)
            
            # 不应该到达这里
            raise last_exception
        
        return wrapper
    return decorator


# ============================================
# 全局限流器实例
# ============================================

# 东方财富接口限流器（较严格）
_eastmoney_limiter = RateLimiter(
    min_interval=2.0,
    jitter_min=1.0,
    jitter_max=3.0
)

# 腾讯财经接口限流器（较宽松）
_tencent_limiter = RateLimiter(
    min_interval=1.0,
    jitter_min=0.5,
    jitter_max=1.5
)

# Akshare 接口限流器
_akshare_limiter = RateLimiter(
    min_interval=2.0,
    jitter_min=1.5,
    jitter_max=3.5
)


# ============================================
# IBKR 专用限流器 (参考 ibkr-datafetcher 实现)
# ============================================

from collections import deque
import threading


class IBKRRateLimiter:
    """
    IBKR 专用请求频率限制器

    基于 ibkr-datafetcher 实现，保护 IBKR API 调用
    满足 D-21, D-22, D-23 要求
    """

    def __init__(
        self,
        hist_requests_per_minute: int = 6,
        news_requests_per_minute: int = 3,
        identical_cooldown: float = 15.0,
        same_contract_limit: int = 6,
        same_contract_window: float = 2.0,
    ) -> None:
        self._hist_rpm = hist_requests_per_minute
        self._news_rpm = news_requests_per_minute
        self._identical_cooldown = identical_cooldown
        self._same_contract_limit = same_contract_limit
        self._same_contract_window = same_contract_window

        self._lock = threading.Lock()
        self._hist_ts: deque = deque()
        self._news_ts: deque = deque()
        self._last_identical: dict = {}
        self._contract_ts: dict = {}

        self._hist_requests = 0
        self._news_requests = 0
        self._total_waits = 0
        self._total_wait_time = 0.0

    def acquire(
        self,
        request_type: str = "hist",
        symbol: str = "",
        exchange: str = "",
        sec_type: str = "STK",
    ) -> None:
        """
        获取请求许可（阻塞等待）

        Args:
            request_type: 请求类型 ("hist" 或 "news")
            symbol: 股票代码
            exchange: 交易所代码
            sec_type: 证券类型
        """
        bucket = "news" if request_type == "news" else "hist"
        rpm = self._news_rpm if bucket == "news" else self._hist_rpm
        dq_global = self._news_ts if bucket == "news" else self._hist_ts
        key = (symbol, exchange, sec_type)

        while True:
            wait = 0.0
            with self._lock:
                now = time.monotonic()
                self._prune_minute(dq_global, now)
                wait = self._wait_for_global(dq_global, rpm, now)
                if symbol:
                    last = self._last_identical.get(key)
                    if last is not None:
                        elapsed = now - last
                        if elapsed < self._identical_cooldown:
                            need = self._identical_cooldown - elapsed
                            wait = max(wait, need)

                    cdq = self._contract_ts.setdefault(symbol, deque())
                    self._prune_window(cdq, now, self._same_contract_window)
                    if len(cdq) >= self._same_contract_limit:
                        oldest = cdq[0]
                        need = oldest + self._same_contract_window - now
                        wait = max(wait, need)

                if wait <= 0:
                    self._grant(bucket, dq_global, symbol, key, now)
                    return

            slept = wait
            with self._lock:
                self._total_waits += 1
            t0 = time.monotonic()
            time.sleep(slept)
            with self._lock:
                self._total_wait_time += time.monotonic() - t0

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            now = time.monotonic()
            self._prune_minute(self._hist_ts, now)
            self._prune_minute(self._news_ts, now)
            hist_n = len(self._hist_ts)
            news_n = len(self._news_ts)
            util_hist = hist_n / self._hist_rpm if self._hist_rpm else 0.0
            util_news = news_n / self._news_rpm if self._news_rpm else 0.0
            utilization = max(util_hist, util_news)
            tw = self._total_waits
            avg = self._total_wait_time / tw if tw else 0.0
            return {
                "hist_requests": self._hist_requests,
                "news_requests": self._news_requests,
                "total_waits": self._total_waits,
                "avg_wait_time": avg,
                "utilization": utilization,
            }

    def _prune_minute(self, dq: deque, now: float) -> None:
        cutoff = now - 60.0
        while dq and dq[0] <= cutoff:
            dq.popleft()

    def _prune_window(self, dq: deque, now: float, window: float) -> None:
        cutoff = now - window
        while dq and dq[0] <= cutoff:
            dq.popleft()

    def _wait_for_global(self, dq: deque, rpm: int, now: float) -> float:
        if len(dq) < rpm:
            return 0.0
        oldest = dq[0]
        return oldest + 60.0 - now

    def _grant(
        self,
        bucket: str,
        dq_global: deque,
        symbol: str,
        key: tuple,
        now: float,
    ) -> None:
        dq_global.append(now)
        if bucket == "hist":
            self._hist_requests += 1
        else:
            self._news_requests += 1
        if symbol:
            self._last_identical[key] = now
            cdq = self._contract_ts.setdefault(symbol, deque())
            self._prune_window(cdq, now, self._same_contract_window)
            cdq.append(now)


# IBKR 限流器全局单例
_ibkr_limiter = IBKRRateLimiter(
    hist_requests_per_minute=6,
    news_requests_per_minute=3,
    identical_cooldown=15.0,
    same_contract_limit=6,
    same_contract_window=2.0,
)


def get_ibkr_limiter() -> IBKRRateLimiter:
    """获取 IBKR 限流器单例"""
    return _ibkr_limiter


def get_eastmoney_limiter() -> RateLimiter:
    """获取东方财富限流器"""
    return _eastmoney_limiter


def get_tencent_limiter() -> RateLimiter:
    """获取腾讯财经限流器"""
    return _tencent_limiter


def get_akshare_limiter() -> RateLimiter:
    """获取 Akshare 限流器"""
    return _akshare_limiter
