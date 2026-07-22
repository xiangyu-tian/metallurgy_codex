"""Provider-neutral chat contract and DeepSeek OpenAI-compatible adapter."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMAdapterError(RuntimeError):
    """Raised when provider configuration or a remote chat request fails."""


_STREAM_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "物流名称"},
            "mass": {"type": "number", "description": "物流质量"},
            "elements": {
                "type": "object",
                "description": "元素名称到质量分数的映射",
                "additionalProperties": {"type": "number"},
            },
        },
        "required": ["name", "mass", "elements"],
    },
}

_TOOL_SCHEMA_OVERRIDES = {
    "A004": {
        "compositions": {
            "type": "object",
            "description": "组分名称到质量分数或摩尔分数的映射",
            "additionalProperties": {"type": "number"},
        },
    },
    "A005": {
        "input_streams": _STREAM_SCHEMA,
        "output_streams": _STREAM_SCHEMA,
    },
}


def _local_environment() -> Dict[str, str]:
    """Read the ignored local provider file without mutating process globals."""
    values = dict(os.environ)
    env_path = Path(__file__).resolve().parents[2] / "backend" / ".env"
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values.setdefault(name.strip(), value.strip())
    return values


def _http_post_json(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error", {}).get("message", body)
        except json.JSONDecodeError:
            detail = body
        raise LLMAdapterError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise LLMAdapterError(f"DeepSeek request failed: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMAdapterError("DeepSeek returned invalid JSON") from exc


def _schema_property(spec: dict) -> dict:
    legacy_type = spec.get("type", "string")
    result = {"type": "string" if legacy_type == "select" else legacy_type}
    description_parts = [
        str(value).strip()
        for value in (
            spec.get("label"), spec.get("description"),
            f"单位: {spec['unit']}" if spec.get("unit") else "",
            f"示例: {spec['placeholder']}" if spec.get("placeholder") else "",
        )
        if value and str(value).strip()
    ]
    if description_parts:
        result["description"] = "；".join(dict.fromkeys(description_parts))
    for key in ("enum", "default", "minimum", "maximum", "minItems", "maxItems"):
        if key in spec:
            result[key] = deepcopy(spec[key])
    if result["type"] == "object":
        result["properties"] = {
            name: _schema_property(child)
            for name, child in spec.get("properties", {}).items()
        }
        if isinstance(spec.get("required"), list):
            result["required"] = list(spec["required"])
    if result["type"] == "array" and spec.get("items"):
        result["items"] = _schema_property(spec["items"])
    return result


def model_tools(registry, model_codes: Optional[Iterable[str]] = None) -> List[dict]:
    """Convert frozen model cards to OpenAI function-tool definitions."""
    selected = set(model_codes or [])
    tools = []
    for card in sorted(registry.list_models(), key=lambda item: item["model_code"]):
        code = card["model_code"]
        if selected and code not in selected:
            continue
        schema = card["input_schema"]
        parameters = {
            "type": "object",
            "properties": {
                name: _schema_property(spec)
                for name, spec in schema.get("properties", {}).items()
            },
            "required": list(schema.get("required", [])),
        }
        parameters["properties"].update(deepcopy(_TOOL_SCHEMA_OVERRIDES.get(code, {})))
        description = "；".join(filter(None, [
            card.get("model_name"), card.get("description"),
            f"适用条件: {card.get('applicable_conditions')}"
            if card.get("applicable_conditions") else "",
        ]))
        tools.append({
            "type": "function",
            "function": {
                "name": code,
                "description": description[:1024],
                "parameters": parameters,
            },
        })
    return tools


class DeepSeekOpenAIAdapter:
    """Small dependency-free adapter for DeepSeek's OpenAI chat endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "deepseek-v4-flash",
        thinking: str = "disabled",
        timeout: float = 120.0,
        transport: Optional[Callable[[str, dict, dict, float], dict]] = None,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.thinking = thinking
        self.timeout = timeout
        self.transport = transport or _http_post_json

    @classmethod
    def from_environment(cls) -> "DeepSeekOpenAIAdapter":
        env = _local_environment()
        return cls(
            api_key=env.get("DEEPSEEK_API_KEY", ""),
            base_url=env.get("DEEPSEEK_OPENAI_BASE_URL", ""),
            model=env.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            thinking=env.get("DEEPSEEK_THINKING", "disabled"),
        )

    def ensure_ready(self) -> None:
        if not self.api_key:
            raise LLMAdapterError("DEEPSEEK_API_KEY is not configured")
        if not self.base_url:
            raise LLMAdapterError("DEEPSEEK_OPENAI_BASE_URL is not configured")
        if self.thinking not in {"enabled", "disabled"}:
            raise LLMAdapterError("DEEPSEEK_THINKING must be enabled or disabled")

    def configuration(self) -> dict:
        return {
            "provider": "deepseek",
            "model": self.model,
            "openai_base_url": self.base_url,
            "thinking": self.thinking,
            "api_key_configured": bool(self.api_key),
        }

    def complete(
        self,
        messages: List[dict],
        *,
        tools: Optional[List[dict]] = None,
        tool_choice=None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> dict:
        self.ensure_ready()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "thinking": {"type": self.thinking},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        response = self.transport(
            f"{self.base_url}/chat/completions",
            {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.api_key}",
            },
            payload,
            self.timeout,
        )
        choices = response.get("choices") or []
        if not choices or not isinstance(choices[0].get("message"), dict):
            raise LLMAdapterError("DeepSeek response does not contain a message")
        choice = choices[0]
        return {
            "id": response.get("id"),
            "model": response.get("model", self.model),
            "message": deepcopy(choice["message"]),
            "finish_reason": choice.get("finish_reason"),
            "usage": deepcopy(response.get("usage")),
        }
