"""B 站 wbi 请求签名（网页客户端标准行为，来自公开 nav 接口）。

仅用于让请求与网页端一致以访问公开内容；限速与风控硬停护栏不受影响。
参考公开社区文档 bilibili-API-collect 的 wbi 签名算法。
"""

from __future__ import annotations

import hashlib
import time
from functools import reduce
from typing import Any
from urllib.parse import urlencode

_MIXIN_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]


class WbiSigner:
    def __init__(self, img_key: str, sub_key: str):
        self.mixin_key = self._mixin(img_key, sub_key)

    @staticmethod
    def _mixin(img_key: str, sub_key: str) -> str:
        raw = img_key + sub_key
        return reduce(lambda s, i: s + raw[i], _MIXIN_TAB, "")[:32]

    @classmethod
    def from_nav(cls, nav_payload: dict[str, Any]) -> "WbiSigner | None":
        wbi = ((nav_payload.get("data") or {}).get("wbi_img") or {})
        img = (wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
        sub = (wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
        if not img or not sub:
            return None
        return cls(img, sub)

    def sign(self, params: dict[str, Any]) -> dict[str, Any]:
        p = {k: v for k, v in params.items()}
        p["wts"] = int(time.time())
        # 值过滤（与网页端一致）
        p = {
            k: (str(v).replace("'", "").replace("!", "").replace("(", "").replace(")", "*") if isinstance(v, str) else v)
            for k, v in p.items()
        }
        items = sorted(p.items())
        query = urlencode(items, quote_via=lambda s, safe, enc=None, err=None: s)  # type: ignore[arg-type]
        p["w_rid"] = hashlib.md5((query + self.mixin_key).encode("utf-8")).hexdigest()
        return p
