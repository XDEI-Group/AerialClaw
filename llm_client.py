"""
llm_client.py  —— 统一 LLM 调用层

所有模块通过 get_client() 取一个 LLMClient 实例，
调用 chat(messages) 即可，无需关心厂商、URL、Key 等细节。

用法：
    from llm_client import get_client

    client = get_client()                        # 用全局 ACTIVE_PROVIDER
    client = get_client(module="planner")        # 用 MODULE_CONFIG["planner"]
    client = get_client(provider="deepseek",     # 直接指定厂商+模型
                        model="deepseek-chat")

    reply = client.chat([
        {"role": "system", "content": "..."},
        {"role": "user",   "content": "..."},
    ])

支持的 api_type：
    "openai_compat"  → 任何兼容 OpenAI /v1/chat/completions 的服务
                       （Ollama / DeepSeek / Moonshot / vLLM / LM Studio …）
"""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from typing import Any


def _strip_thinking(text: str) -> str:
    """
    过滤推理模型（如 qwen3、deepseek-r1）输出的 <think>...</think> 推理链，
    只保留最终回复内容。
    """
    # 去掉 <think>...</think> 块（包括跨行）
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
    return text.strip()

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import config as _cfg


# ── LLMClient ────────────────────────────────────────────────────────────────

class LLMClient:
    """
    统一 LLM 客户端。
    屏蔽厂商差异，对外只暴露 chat() 方法。
    """

    def __init__(self, provider_cfg: dict, model: str):
        """
        Args:
            provider_cfg: PROVIDERS[name] 字典
            model:        具体使用的模型 ID
        """
        self._api_type = provider_cfg["api_type"]
        self._base_url = provider_cfg["base_url"].rstrip("/")
        self._api_key  = provider_cfg["api_key"]
        self._model    = model
        self._timeout  = provider_cfg.get("timeout", 60)

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_url(self) -> str:
        return self._base_url

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        on_chunk: Any = None,
        **kwargs: Any,
    ) -> str:
        """
        发送多轮对话请求，返回 assistant 回复文本。

        Args:
            messages:    消息列表，格式 [{"role": "system"|"user"|"assistant", "content": str}]
            temperature: 温度参数，默认 0.7
            max_tokens:  最大输出 token 数，None 表示不限制
            on_chunk:    流式回调 on_chunk(text_fragment: str)，每收到一个 token 就调用
            **kwargs:    其他透传给 API 的参数

        Returns:
            str: assistant 回复内容

        Raises:
            RuntimeError: 网络错误或响应解析失败
        """
        if self._api_type == "openai_compat":
            return self._chat_openai_compat(messages, temperature, max_tokens, on_chunk=on_chunk, **kwargs)
        else:
            raise NotImplementedError(f"api_type '{self._api_type}' 暂不支持")

    # ── 内部实现 ──────────────────────────────────────────────────────────────

    def _chat_openai_compat(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int | None,
        on_chunk=None,
        **kwargs,
    ) -> str:
        """
        调用 OpenAI 兼容接口 POST /v1/chat/completions。

        使用流式模式（stream=True）逐块读取，避免推理模型长时间等待导致连接断开。
        最终拼接所有 delta.content 返回完整文本（过滤掉 <think> 推理链）。
        """
        url = f"{self._base_url}/chat/completions"

        payload: dict = {
            "model":       self._model,
            "messages":    messages,
            "stream":      True,   # 流式，避免推理模型超时断连
            "temperature": temperature,
            **kwargs,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            chunks: list[str] = []
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload_str = line[5:].strip()
                    if payload_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload_str)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            chunks.append(content)
                            if on_chunk:
                                on_chunk(content)
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

            full_text = "".join(chunks).strip()
            # 过滤掉推理模型的 <think>...</think> 块，只保留最终回复
            full_text = _strip_thinking(full_text)
            return full_text

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"[LLMClient] HTTP {e.code} from {url}\n{body[:400]}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"[LLMClient] 无法连接到 {url}：{e.reason}"
            ) from e

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str = "auto",
        temperature: float = 0.3,
    ) -> dict:
        """
        发送工具调用请求（非流式），返回 LLM 的完整响应结构。

        与 chat() 的区别：
            - 非流式模式（stream=False）：必须等待 LLM 完成后才能读取 tool_calls
            - 返回完整 message 对象而非纯文本，以便调用方解析 tool_calls

        注意（Ollama qwen3.5:9b）：
            推理模型在非流式模式下可能超时断连。
            若遇到此问题，建议换用支持 function calling 的非推理模型
            （如 qwen2.5:7b 或云端 deepseek-chat）。

        Args:
            messages    : 消息列表
            tools       : OpenAI Function Calling 格式的工具定义列表
            tool_choice : "auto" / "none" / 指定工具名，默认 "auto"
            temperature : 温度参数，工具调用场景建议低温，默认 0.3

        Returns:
            dict: {
                "finish_reason": str,   # "stop" | "tool_calls" | "length" | ...
                "message": {
                    "role":       "assistant",
                    "content":    str | None,
                    "tool_calls": list[dict] | None   # 有工具调用时存在
                }
            }

        Raises:
            RuntimeError: 网络错误或响应解析失败
        """
        if self._api_type == "openai_compat":
            return self._chat_with_tools_openai_compat(
                messages, tools, tool_choice, temperature
            )
        else:
            raise NotImplementedError(f"api_type '{self._api_type}' 暂不支持 chat_with_tools")

    def _chat_with_tools_openai_compat(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_choice: str,
        temperature: float,
    ) -> dict:
        """
        非流式调用 OpenAI 兼容接口，解析 tool_calls。

        注意：此方法使用 stream=False，推理模型可能因耗时过长导致连接断开。
        建议工具调用场景使用响应快的非推理模型（如 qwen2.5:7b）。
        """
        url = f"{self._base_url}/chat/completions"

        payload: dict = {
            "model":       self._model,
            "messages":    messages,
            "tools":       tools,
            "tool_choice": tool_choice,
            "stream":      False,
            "temperature": temperature,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")

            response_json = json.loads(body)
            choice = response_json["choices"][0]
            finish_reason = choice.get("finish_reason", "stop")
            message = choice.get("message", {})

            # 过滤推理链
            content = message.get("content") or ""
            if content:
                content = _strip_thinking(content)
                message = dict(message)
                message["content"] = content

            return {
                "finish_reason": finish_reason,
                "message":       message,
            }

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"[LLMClient.chat_with_tools] HTTP {e.code} from {url}\n{body[:400]}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"[LLMClient.chat_with_tools] 无法连接到 {url}：{e.reason}"
            ) from e
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise RuntimeError(
                f"[LLMClient.chat_with_tools] 响应解析失败：{e}"
            ) from e

    def __repr__(self) -> str:
        return f"<LLMClient provider={self._base_url} model={self._model}>"


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def get_client(
    module:   str | None = None,
    provider: str | None = None,
    model:    str | None = None,
) -> LLMClient:
    """
    获取 LLMClient 实例。优先级（高 → 低）：

        1. 直接传入的 provider / model 参数
        2. MODULE_CONFIG[module] 中指定的配置
        3. ACTIVE_PROVIDER + provider.default_model

    Args:
        module:   模块名称，例如 "planner" / "doc_generator"
                  用于查询 MODULE_CONFIG，None 表示跳过
        provider: 厂商名称，覆盖 module 配置，例如 "deepseek"
        model:    模型 ID，覆盖 provider.default_model

    Returns:
        LLMClient 实例

    Examples:
        get_client()                             # 全局默认
        get_client(module="planner")             # 用 planner 的模块配置
        get_client(provider="openai")            # 强制用 openai 厂商
        get_client(provider="deepseek",
                   model="deepseek-coder")       # 指定厂商 + 模型
    """
    # Step 1：确定 provider 名称
    resolved_provider = (
        provider
        or _resolve_module_field(module, "provider")
        or _cfg.ACTIVE_PROVIDER
    )

    if resolved_provider not in _cfg.PROVIDERS:
        raise ValueError(
            f"[LLMClient] 未知厂商 '{resolved_provider}'，"
            f"可选值：{list(_cfg.PROVIDERS.keys())}"
        )
    provider_cfg = _cfg.PROVIDERS[resolved_provider]

    # Step 2：确定模型
    resolved_model = (
        model
        or _resolve_module_field(module, "model")
        or provider_cfg["default_model"]
    )

    return LLMClient(provider_cfg, resolved_model)


def _resolve_module_field(module: str | None, field: str) -> str | None:
    """从 MODULE_CONFIG 读取指定模块的某字段值（None 表示未配置）。"""
    if module is None:
        return None
    return _cfg.MODULE_CONFIG.get(module, {}).get(field)
