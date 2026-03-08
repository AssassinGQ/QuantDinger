"""Market hours for EastMoney trading."""

from datetime import datetime, time, timedelta
from typing import Tuple, Optional
from zoneinfo import ZoneInfo


class MarketHours:
    """Market trading hours."""

    HONG_KONG = {
        "name": "港股",
        "sessions": [
            (time(9, 30), time(12, 0)),
            (time(13, 0), time(16, 0)),
        ],
        "timezone": "Asia/Hong_Kong"
    }

    CHINA_A = {
        "name": "A股",
        "sessions": [
            (time(9, 30), time(11, 30)),
            (time(13, 0), time(15, 0)),
        ],
        "timezone": "Asia/Shanghai"
    }

    BOND = {
        "name": "可转债",
        "sessions": [
            (time(9, 30), time(11, 30)),
            (time(13, 0), time(15, 0)),
        ],
        "timezone": "Asia/Shanghai"
    }

    ETF = {
        "name": "ETF",
        "sessions": [
            (time(9, 30), time(11, 30)),
            (time(13, 0), time(15, 0)),
        ],
        "timezone": "Asia/Shanghai"
    }

    @classmethod
    def get_market_hours(cls, market_type: str) -> dict:
        """Get market hours for market type."""
        market_type = market_type.upper() if market_type else ""
        if market_type in ("HKSTOCK", "HK", "HKSE"):
            return cls.HONG_KONG
        if market_type in ("BOND", "CONVERTIBLE"):
            return cls.BOND
        if market_type in ("ETF", "FUND"):
            return cls.ETF
        return cls.CHINA_A

    @classmethod
    def _to_market_time(cls, market: dict, dt: Optional[datetime] = None) -> datetime:
        """Convert to market timezone."""
        tz = ZoneInfo(market["timezone"])
        if dt is None:
            return datetime.now(tz)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)

    @classmethod
    def is_trading_time(cls, market_type: str, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """Check if currently in trading time."""
        market = cls.get_market_hours(market_type)
        market_dt = cls._to_market_time(market, dt)
        current_time = market_dt.time()

        if market_dt.weekday() >= 5:
            return False, f"{market['name']} 当前非交易时间（周末）"

        for start, end in market["sessions"]:
            if start <= current_time <= end:
                return True, ""

        return False, f"{market['name']} 当前非交易时间"

    @classmethod
    def is_market_open(cls, market_type: str) -> bool:
        """Check if market is open."""
        is_open, _ = cls.is_trading_time(market_type)
        return is_open

    @classmethod
    def get_next_open_time(cls, market_type: str, dt: Optional[datetime] = None) -> datetime:
        """Get next market open time."""
        market = cls.get_market_hours(market_type)
        market_dt = cls._to_market_time(market, dt)
        current_time = market_dt.time()

        for start, _end in market["sessions"]:
            if start > current_time:
                return market_dt.replace(
                    hour=start.hour, minute=start.minute, second=0, microsecond=0
                )

        next_day = market_dt + timedelta(days=1)
        first_start = market["sessions"][0][0]
        return next_day.replace(
            hour=first_start.hour, minute=first_start.minute, second=0, microsecond=0
        )
