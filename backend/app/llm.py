"""LLM 客户端：OpenAI 兼容的 chat/completions，只要求返回 JSON。

不引入新依赖，复用 httpx。所有失败统一折成 LLMError，调用方据此降级。
key 不做全局单例：显式从请求头或环境变量取，避免「谁配了 key 谁的机器就变了」。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "https://api.deepseek.com"
# 选衣这种小任务用 chat 更省更快：flash 是推理模型，每次多烧 100–170 个 reasoning token
# （实测 chat 735ms / 6 completion tokens，flash 1.2–1.5s）。EW_LLM_MODEL 可覆盖。
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TIMEOUT = 15.0
# 这些模型带 reasoning tokens，预算太小会把正文挤成空字符串（finish_reason=length）
DEFAULT_MAX_TOKENS = 800


class LLMError(Exception):
    """模型侧任何失败。reason 会进 fallback_reason，必须是稳定短码。"""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    api_key: str
    timeout: float = DEFAULT_TIMEOUT
    max_tokens: int = DEFAULT_MAX_TOKENS


def key_fingerprint(api_key: str) -> str:
    """日志里只记指纹，绝不记明文。"""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:8]


def resolve_llm_config(header_key: str | None) -> LLMConfig | None:
    """请求头优先，其次环境变量；都没有返回 None（调用方走规则，不算错误）。"""
    key = (header_key or "").strip() or os.environ.get("EW_LLM_KEY", "").strip()
    if not key:
        return None

    base_url = os.environ.get("EW_LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("EW_LLM_MODEL", DEFAULT_MODEL)
    raw_max_tokens = os.environ.get("EW_LLM_MAX_TOKENS", "").strip()
    try:
        max_tokens = int(raw_max_tokens) if raw_max_tokens else DEFAULT_MAX_TOKENS
    except ValueError:
        max_tokens = DEFAULT_MAX_TOKENS
    return LLMConfig(
        base_url=base_url, model=model, api_key=key, max_tokens=max_tokens
    )


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _usage_from(body: dict) -> dict[str, int | None]:
    """取不到就记 None——0 和「没有这个数据」不是一回事。"""
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return {"prompt_tokens": None, "completion_tokens": None}
    return {
        "prompt_tokens": _as_int(usage.get("prompt_tokens")),
        "completion_tokens": _as_int(usage.get("completion_tokens")),
    }


def _parse_content(content: str) -> dict:
    """模型有时会裹 ```json 围栏，这里容忍一下；仍解析不了就算 bad_json。"""
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise LLMError("bad_json", "模型返回的不是合法 JSON") from exc
    if not isinstance(data, dict):
        raise LLMError("bad_structure", "模型返回的 JSON 不是对象")
    return data


async def _post(config: LLMConfig, payload: dict) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=config.timeout) as client:
            return await client.post(
                f"{config.base_url}/chat/completions", json=payload, headers=headers
            )
    except httpx.TimeoutException as exc:
        raise LLMError("timeout", "模型请求超时") from exc
    except httpx.HTTPError as exc:
        raise LLMError("network", f"模型请求失败：{exc.__class__.__name__}") from exc


async def chat_json(config: LLMConfig, system: str, user: str) -> tuple[dict, dict[str, int | None]]:
    """返回 (解析后的 JSON, usage)。usage 取不到时字段为 None。"""
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
    }

    response = await _post(config, payload)

    # 有的兼容实现不认 response_format；按提示词+解析兜底，重试一次去掉它
    if response.status_code == 400 and "response_format" in (response.text or ""):
        payload.pop("response_format", None)
        response = await _post(config, payload)

    if response.status_code == 429:
        raise LLMError("rate_limited", "模型限流")
    if response.status_code >= 500:
        raise LLMError(f"upstream_{response.status_code}", "模型服务异常")
    if response.status_code != 200:
        raise LLMError(f"http_{response.status_code}", "模型请求被拒绝")

    try:
        body = response.json()
    except ValueError as exc:
        raise LLMError("bad_json", "模型返回的不是 JSON") from exc

    try:
        choice = body["choices"][0]
        message = choice["message"]
        content = message.get("content")
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise LLMError("bad_structure", "模型响应结构不对") from exc

    # reasoning tokens 会吃掉预算：截断时 content 可能是空串，
    # 直接 json.loads("") 会崩，所以先判截断再判空。
    if finish_reason == "length":
        raise LLMError("truncated", "模型输出被 max_tokens 截断")
    if not (content or "").strip():
        raise LLMError("truncated", "模型返回的正文为空（可能预算耗在推理上）")

    # 只解析 content，忽略 reasoning_content
    return _parse_content(content), _usage_from(body)
