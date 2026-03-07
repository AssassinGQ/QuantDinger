from dataclasses import dataclass


@dataclass
class USmartConfig:
    channel_id: str
    private_key: str
    public_key: str
    phone_number: str
    password: str
    area_code: str = "86"
    lang: str = "1"
    is_pro: bool = False
    base_url: str = "https://open-jy.yxzq.com"
    timeout: float = 15.0
