"""
tools/tool_call_loop.py  —— 多轮工具调用循环状态机

实现 OpenAI Function Calling 标准的多轮对话循环：

    messages → LLM → tool_calls? → execute → append results → LLM → ... → stop

状态转移：
    RUNNING  : LLM 返回 tool_calls，继续循环执行工具
    DONE     : LLM 返回 finish_reason="stop"，退出循环返回最终回复
    MAX_ITER : 超过最大轮数，强制退出

用法：
    from tools.tool_call_loop import tool_call_loop
    from tools import ToolRegistry, ToolExecutor

    final_reply = tool_call_loop(
        client=client,
        messages=messages,
        tool_registry=tool_registry,
        max_iterations=5,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tools.executor import ToolExecutor
from tools.registry import ToolRegistry

if TYPE_CHECKING:
    from llm_client import LLMClient


def tool_call_loop(
    client: "LLMClient",
    messages: list[dict],
    tool_registry: ToolRegistry,
    max_iterations: int = 8,
    temperature: float = 0.3,
    tool_choice: str = "auto",
) -> str:
    """
    多轮工具调用循环，直到 LLM 返回 stop 或达到最大轮数。

    Args:
        client        : LLMClient 实例（需支持 chat_with_tools()）
        messages      : 初始消息列表（system + user），函数内部会追加 assistant/tool 消息
        tool_registry : 工具注册表
        max_iterations: 最大工具调用轮数，超过后返回当前 LLM 最后回复
        temperature   : LLM 温度参数
        tool_choice   : "auto"（LLM 自主决定）/ "none"（禁用工具）/ 指定工具名

    Returns:
        str: LLM 最终回复文本（finish_reason=stop 时的 content）

    Raises:
        RuntimeError: LLM 调用失败（网络错误等）
    """
    executor = ToolExecutor(tool_registry)
    tool_defs = tool_registry.get_tool_definitions()

    # 对话历史的工作副本（不修改调用方传入的列表）
    history = list(messages)

    for iteration in range(1, max_iterations + 1):
        print(f"  [ToolCallLoop] 轮次 {iteration}/{max_iterations} —— 调用 LLM...")

        response = client.chat_with_tools(
            messages=history,
            tools=tool_defs,
            tool_choice=tool_choice,
            temperature=temperature,
        )

        finish_reason = response.get("finish_reason", "stop")
        message       = response.get("message", {})
        content       = message.get("content") or ""
        tool_calls    = message.get("tool_calls") or []

        # ── 1. 追加 assistant 消息到历史 ──────────────────────────────────────
        # 注意：即使 content 为空（纯 tool_calls 回复），也要追加
        assistant_msg: dict = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        history.append(assistant_msg)

        # ── 2. 判断是否继续 ────────────────────────────────────────────────────
        if finish_reason == "tool_calls" or tool_calls:
            if not tool_calls:
                # 声称要调用工具但没有 tool_calls，视为完成
                print(f"  [ToolCallLoop] finish_reason=tool_calls 但 tool_calls 为空，提前结束")
                return content

            print(f"  [ToolCallLoop] LLM 请求调用 {len(tool_calls)} 个工具")

            # 执行工具
            results = executor.execute_tool_calls(tool_calls)

            # 追加 tool 消息到历史
            tool_messages = ToolExecutor.results_to_messages(results)
            history.extend(tool_messages)

            # 继续下一轮
            continue

        else:
            # finish_reason == "stop" 或其他终止条件
            print(f"  [ToolCallLoop] LLM 完成，finish_reason={finish_reason}")
            return content

    # 超过最大轮数，返回最后一次 LLM 的内容
    print(f"  [ToolCallLoop] 达到最大轮数 {max_iterations}，强制返回")
    last_assistant = next(
        (m["content"] for m in reversed(history) if m["role"] == "assistant"),
        "",
    )
    return last_assistant or ""
