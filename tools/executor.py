"""
tools/executor.py  —— 工具执行器

职责：
    - 解析 LLM 返回的 tool_calls 列表
    - 按工具名称路由到 ToolRegistry 中的具体 Tool 实例
    - 执行工具并收集 ToolResult
    - 将结果转换为 tool role 消息列表，供追加到对话历史

流程：
    LLM 返回 tool_calls
        ↓
    ToolExecutor.execute_tool_calls(tool_calls)
        ↓
    [ToolResult, ToolResult, ...]
        ↓
    ToolExecutor.results_to_messages([...])
        ↓
    [{"role": "tool", "tool_call_id": ..., "content": ...}, ...]
"""

from __future__ import annotations

import json

from tools.base_tool import ToolResult
from tools.registry import ToolRegistry


class ToolExecutor:
    """
    工具执行器。

    将 LLM 的 tool_calls 分发给对应工具执行，返回 tool role 消息。

    Args:
        registry: ToolRegistry 实例，包含所有可用工具
    """

    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def execute_tool_calls(self, tool_calls: list[dict]) -> list[ToolResult]:
        """
        批量执行 LLM 返回的 tool_calls。

        Args:
            tool_calls: LLM message.tool_calls 列表，每项格式：
                {
                    "id": "call_xxxx",
                    "type": "function",
                    "function": {
                        "name": "tool_name",
                        "arguments": "{\"key\": \"value\"}"  # JSON 字符串
                    }
                }

        Returns:
            list[ToolResult]: 每个 tool_call 对应一个 ToolResult，顺序与输入一致
        """
        results: list[ToolResult] = []

        for tc in tool_calls:
            tool_call_id = tc.get("id", "")
            func_info    = tc.get("function", {})
            tool_name    = func_info.get("name", "")
            args_str     = func_info.get("arguments", "{}")

            # 解析参数 JSON
            try:
                kwargs = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError as e:
                results.append(ToolResult(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    content="",
                    success=False,
                    error=f"参数 JSON 解析失败: {e}",
                ))
                continue

            # 路由到工具
            if not self._registry.has(tool_name):
                results.append(ToolResult(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    content="",
                    success=False,
                    error=f"未知工具: '{tool_name}'，已注册: {[t.name for t in self._registry]}",
                ))
                continue

            tool = self._registry.get(tool_name)
            result = tool.run(tool_call_id=tool_call_id, **kwargs)
            results.append(result)

            _status = "OK" if result.success else f"FAIL({result.error[:60]})"
            print(f"  [ToolExecutor] {tool_name}({_fmt_kwargs(kwargs)}) → {_status}")

        return results

    @staticmethod
    def results_to_messages(results: list[ToolResult]) -> list[dict]:
        """
        将 ToolResult 列表转换为 tool role 消息列表。

        追加到对话历史后即可进行下一轮 LLM 调用：
            messages += ToolExecutor.results_to_messages(results)

        Args:
            results: execute_tool_calls() 的返回值

        Returns:
            list[dict]: tool role 消息列表
        """
        return [r.to_message() for r in results]


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _fmt_kwargs(kwargs: dict, max_len: int = 80) -> str:
    """将 kwargs 格式化为紧凑字符串，用于日志打印。"""
    s = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
    return s[:max_len] + "..." if len(s) > max_len else s
