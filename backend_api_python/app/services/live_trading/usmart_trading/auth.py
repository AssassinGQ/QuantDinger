import base64
import json
import time
import uuid
from typing import Tuple

import rsa


class USmartAuth:
    def __init__(self, public_key: str, private_key: str, channel_id: str, lang: str = "1"):
        self.channel_id = channel_id
        self.lang = lang
        self._pub_key = self._load_public_key(public_key)
        self._priv_key = self._load_private_key(private_key)

    def _load_public_key(self, pub_key_str: str) -> rsa.PublicKey:
        return rsa.PublicKey.load_pkcs1(pub_key_str.encode('utf-8'))

    def _load_private_key(self, priv_key_str: str) -> rsa.PrivateKey:
        return rsa.PrivateKey.load_pkcs1(priv_key_str.encode('utf-8'))

    def encrypt_credentials(self, phone_number: str, password: str) -> Tuple[str, str]:
        encrypted_phone = rsa.encrypt(phone_number.encode('utf-8'), self._pub_key)
        encrypted_pass = rsa.encrypt(password.encode('utf-8'), self._pub_key)
        return (
            base64.b64encode(encrypted_phone).decode('utf-8'),
            base64.b64encode(encrypted_pass).decode('utf-8')
        )

    def generate_request_id(self) -> str:
        return str(uuid.uuid4().int)[:19]

    def generate_timestamp(self) -> str:
        return str(int(time.time()))

    def sign(self, payload: dict) -> str:
        sign_content = json.dumps(payload, separators=(',', ':'))
        signature = rsa.sign(sign_content.encode('utf-8'), self._priv_key, 'MD5')
        return base64.b64encode(signature).decode('utf-8')

    def build_headers(self, path: str, payload: dict) -> dict:
        del path
        return {
            "X-Lang": self.lang,
            "X-Request-Id": self.generate_request_id(),
            "X-Channel": self.channel_id,
            "X-Time": self.generate_timestamp(),
            "X-Sign": self.sign(payload)
        }
