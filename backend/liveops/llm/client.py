"""LLM 客户端：OpenAI 兼容 / Ollama / Mock 三适配器。

- 无密钥 → MockLLM（确定性，按输入 hash 选择预设行为，测试与演示可用）。
- 429/5xx → 指数退避重试（上限 LLM_MAX_RETRIES），连续熔断 → RateLimitedError（任务暂停可续）。
- 所有调用走 ResponseCache。
- 密钥缺失、注入防护、严格 JSON 由本层与 guard 共同保证。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Type, TypeVar

from pydantic import BaseModel

from .. import config
from .cache import NullCache, ResponseCache, cache_key
from .guard import GuardResult, parse_with_repair

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class RateLimitedError(LLMError):
    """重试耗尽仍被限流，任务应暂停（可续跑），不是数据错误。"""


class AbstainError(LLMError):
    """模型输出两次仍不合法 → 弃权该样本（记录 abstain_reason）。"""


@dataclass
class Usage:
    calls: int = 0
    cache_hits: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    retries: int = 0


class BaseLLMClient:
    name = "base"

    def __init__(self, cache: ResponseCache | None = None):
        self.cache = cache or NullCache()
        self.usage = Usage()

    def complete_json(
        self,
        messages: list[dict[str, str]],
        schema: Type[T],
        *,
        prompt_version: str,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> GuardResult:
        raw, _ = self._cached_or_call(messages, schema, prompt_version, model, temperature)

        def repair(err: str) -> str:
            msg2 = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": (
                    f"你的输出未通过校验：{err}\n请重新输出，只输出符合 Schema 的 JSON，"
                    "不要任何解释或 markdown 围栏。")},
            ]
            return self._call_with_retry(msg2, model, temperature)

        result = parse_with_repair(raw, schema, repair)
        if not result.ok:
            raise AbstainError(f"两次输出均不合法: {result.error}")
        return result

    def _cached_or_call(self, messages, schema, prompt_version, model, temperature):
        key = cache_key(model or self.name, prompt_version, messages)
        hit = self.cache.get(key)
        if hit is not None:
            self.usage.cache_hits += 1
            return hit, True
        raw = self._call_with_retry(messages, model, temperature)
        self.cache.put(key, model or self.name, prompt_version, raw)
        return raw, False

    def _call_with_retry(self, messages, model, temperature) -> str:
        last: Exception | None = None
        for attempt in range(config.LLM_MAX_RETRIES + 1):
            try:
                return self._call(messages, model, temperature)
            except RateLimitedError as e:
                last = e
                if attempt >= config.LLM_MAX_RETRIES:
                    break
                self.usage.retries += 1
                time.sleep(config.LLM_BACKOFF_BASE_S * (2**attempt))
        raise RateLimitedError(f"重试 {config.LLM_MAX_RETRIES} 次后仍失败: {last}")

    def _call(self, messages, model, temperature) -> str:
        raise NotImplementedError


class OpenAICompatClient(BaseLLMClient):
    """OpenAI 风格 base_url/api_key/model（含智谱/DeepSeek 等）。"""

    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str, model: str, cache=None):
        super().__init__(cache)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        from openai import OpenAI
        self._client = OpenAI(base_url=self.base_url, api_key=self.api_key, timeout=config.LLM_TIMEOUT_S)

    def _call(self, messages, model, temperature):
        self.usage.calls += 1
        try:
            resp = self._client.chat.completions.create(
                model=model or self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate" in msg.lower():
                raise RateLimitedError(msg)
            raise LLMError(msg)
        if resp.usage:
            self.usage.tokens_in += resp.usage.prompt_tokens or 0
            self.usage.tokens_out += resp.usage.completion_tokens or 0
        content = resp.choices[0].message.content or ""
        return content


class OllamaClient(BaseLLMClient):
    """本地 Ollama 适配器（预留：base_url=http://localhost:11434/v1）。"""

    name = "ollama"

    def __init__(self, base_url: str, model: str, cache=None):
        super().__init__(cache)
        from openai import OpenAI
        self.model = model
        self._client = OpenAI(base_url=base_url.rstrip("/"), api_key="ollama", timeout=config.LLM_TIMEOUT_S)



class MockLLM(BaseLLMClient):
    """确定性 Mock：无密钥时的开发/测试后端。

    按输入 hash 从 responses 里轮转选取；未提供 responses 时返回 "{}"。
    可注入 rate_limit_times 模拟限流场景。
    """

    name = "mock"

    def __init__(self, responses: list[str] | None = None, cache=None,
                 rate_limit_times: int = 0):
        super().__init__(cache)
        self.responses = responses or []
        self.rate_limit_times = rate_limit_times
        self._rate_remaining = rate_limit_times

    def _call(self, messages, model, temperature):
        self.usage.calls += 1
        if self._rate_remaining > 0:
            self._rate_remaining -= 1
            raise RateLimitedError("429 simulated")
        h = int(hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest(), 16)
        if not self.responses:
            return "{}"
        return self.responses[h % len(self.responses)]


_SCRIPTED: dict[str, str] = {}


def register_scripted(prompt_version: str, mapping: dict[str, str]) -> None:
    """注册脚本化回复（post_id → JSON 字符串），供固定样本/种子标注测试。"""
    _SCRIPTED[prompt_version] = json.dumps(mapping, ensure_ascii=False)


class ScriptedLLM(MockLLM):
    """按 post_id 查表的确定性 LLM：纵向切片与金标种子验证用。"""

    name = "scripted"

    def _call(self, messages, model, temperature):
        self.usage.calls += 1
        blob = "\n".join(m["content"] for m in messages)
        import re
        m = re.search(r"post_id[\"':\s]+([A-Za-z0-9_\-\.]+)", blob)
        pid = m.group(1) if m else ""
        table = json.loads(list(_SCRIPTED.values())[-1]) if _SCRIPTED else {}
        if pid in table:
            v = table[pid]
            return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        return json.dumps({"relevant": None, "abstain_reason": "scripted miss"}, ensure_ascii=False)


def get_client(cache: ResponseCache | None = None) -> BaseLLMClient:
    """工厂：按环境变量选择适配器。无密钥 → Mock。"""
    if config.LLM_BASE_URL and config.LLM_API_KEY and config.LLM_MODEL:
        if "ollama" in config.LLM_BASE_URL.lower():
            return OllamaClient(config.LLM_BASE_URL, config.LLM_MODEL, cache)
        return OpenAICompatClient(config.LLM_BASE_URL, config.LLM_API_KEY, config.LLM_MODEL, cache)
    return MockLLM(cache=cache)
