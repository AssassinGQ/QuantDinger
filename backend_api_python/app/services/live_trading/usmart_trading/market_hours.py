from datetime import datetime, time
from typing import Tuple


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
    def is_trading_time(cls, market_type: str, dt: datetime = None) -> Tuple[bool, str]:
        if dt is None:
            dt = datetime.now()

        market = cls.get_market_hours(market_type)
        current_time = dt.time()

        for start, end in market["sessions"]:
            if start <= current_time <= end:
                return True, ""

        return False, "%s 当前非交易时间" % market["name"]

    @classmethod
    def get_next_open_time(cls, market_type: str, dt: datetime = None) -> datetime:
        if dt is None:
            dt = datetime.now()

        market = cls.get_market_hours(market_type)
        current_time = dt.time()

        for start, end in market["sessions"]:
            if start > current_time:
                return dt.replace(hour=start.hour, minute=start.minute, second=0)

        return dt.replace(hour=9, minute=30, second=0)
