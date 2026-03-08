from datetime import datetime, time, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo


class MarketHours:
    HONG_KONG = {
        "name": "港股",
        "sessions": [
            (time(9, 30), time(12, 0)),
            (time(13, 0), time(16, 0)),
        ],
        "timezone": "Asia/Hong_Kong"
    }

    US = {
        "name": "美股",
        "sessions": [
            (time(9, 30), time(16, 0)),
        ],
        "timezone": "America/New_York"
    }

    CHINA = {
        "name": "A股",
        "sessions": [
            (time(9, 30), time(11, 30)),
            (time(13, 0), time(15, 0)),
        ],
        "timezone": "Asia/Shanghai"
    }

    @classmethod
    def get_market_hours(cls, market_type: str) -> dict:
        market_type = market_type.upper()
        if market_type in ("HKSTOCK", "HK", "HKSE"):
            return cls.HONG_KONG
        if market_type in ("USSTOCK", "US", "NASDAQ", "NYSE"):
            return cls.US
        if market_type in ("ASHARE", "CN", "SH", "SZ"):
            return cls.CHINA
        return cls.HONG_KONG

    @classmethod
    def _to_market_time(cls, market: dict, dt: Optional[datetime] = None) -> datetime:
        tz = ZoneInfo(market["timezone"])
        if dt is None:
            return datetime.now(tz)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)

    @classmethod
    def is_trading_time(cls, market_type: str, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        market = cls.get_market_hours(market_type)
        market_dt = cls._to_market_time(market, dt)
        current_time = market_dt.time()

        if market_dt.weekday() >= 5:
            return False, "%s 当前非交易时间（周末）" % market["name"]

        for start, end in market["sessions"]:
            if start <= current_time <= end:
                return True, ""

        return False, "%s 当前非交易时间" % market["name"]

    @classmethod
    def get_next_open_time(cls, market_type: str, dt: Optional[datetime] = None) -> datetime:
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
