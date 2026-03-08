"""
EastMoney (东方财富) Trading Configuration.

Provides configuration dataclass for EastMoney broker connection.
"""

from dataclasses import dataclass


@dataclass
class EFConfig:
    """Configuration for EastMoney broker connection."""

    account_id: str
    password: str
    market: str = "ab"
    token: str = ""
    base_url: str = ""
    timeout: float = 15.0
