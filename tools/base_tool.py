"""
tools/base_tool.py  —— Tool 抽象基类

所有工具均继承 BaseTool，实现 name/description/parameters_schema/run() 即可。

数据结构：
    ToolDefinition  : OpenAI Function Calling 格式的工具描述（用于 LLM tools 参数）
    ToolResult      : 工具执行结果（用于构造 tool role 消息）

设计原则：
    - Tool 只做查询/计算，不执行物理动作（那是 Skill 的职责）
    - run() 永不抛出异常，错误通过 ToolResult.error 返回
    - 所有输入参数通过 kwargs 传入，与 JSON Schema 对应
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """
    工具执行结果。

    Attributes:
        tool_call_id : 对应的 tool_call id（从 LLM tool_calls 响应中取）
        tool_name    : 工具名称
        content      : 执行结果（字符串，JSON 序列化后传回 LLM）
        success      : 是否执行成功
        error        : 错误信息（success=False 时填写）
    """
    tool_call_id: str
    tool_name: str
    content: str
    success: bool = True
    error: str = ""

    def to_message(self) -> dict:
        """
        转换为 OpenAI tool role 消息格式，用于追加到对话历史。

        Returns:
            {"role": "tool", "tool_call_id": str, "content": str}
        """
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content if self.success else f"[ERROR] {self.error}",
        }


@dataclass
class ToolDefinition:
    """
    OpenAI Function Calling 格式的工具定义。

    Attributes:
        name        : 工具名称（snake_case，与 run() 类一致）
        description : 工具功能说明（给 LLM 看）
        parameters  : JSON Schema 格式的参数描述
    """
    name: str
    description: str
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}, "required": []})

    def to_openai_format(self) -> dict:
        """
        转换为 OpenAI tools 列表元素格式：

            {
                "type": "function",
                "function": {
                    "name": ...,
                    "description": ...,
                    "parameters": { JSON Schema }
                }
            }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ── 抽象基类 ──────────────────────────────────────────────────────────────────

class BaseTool(ABC):
    """
    所有工具的抽象基类。

    子类必须实现：
        name            (property) : 工具名称，snake_case
        description     (property) : 功能描述
        parameters_schema (property): JSON Schema 格式参数
        _run(**kwargs)             : 实际执行逻辑，返回可序列化对象

    子类不应覆盖：
        run()   : 统一错误处理包装
        definition() : 构造 ToolDefinition
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称（snake_case），与 JSON Schema function name 一致。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述，给 LLM 阅读，说明工具能做什么、何时调用。"""

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        """
        JSON Schema 格式的参数描述。

        示例：
            {
                "type": "object",
                "properties": {
                    "robot_id": {
                        "type": "string",
                        "description": "机器人 ID，例如 UAV_1"
                    }
                },
                "required": ["robot_id"]
            }
        """

    def _run(self, **kwargs: Any) -> Any:
        """
        实际执行逻辑。子类应覆盖此方法（可增加具名关键字参数）。

        Args:
            **kwargs: 与 parameters_schema 中定义的参数对应

        Returns:
            任意可 JSON 序列化的对象（dict/list/str/int/float/bool）

        Raises:
            可以抛出任何异常，run() 会捕获并转换为 ToolResult.error
        """
        raise NotImplementedError(f"{self.__class__.__name__}._run() 未实现")

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def run(self, tool_call_id: str, **kwargs: Any) -> ToolResult:
        """
        执行工具，统一异常处理。

        Args:
            tool_call_id : LLM 分配的 tool_call id
            **kwargs     : 工具参数（从 LLM tool_calls 的 arguments JSON 解析）

        Returns:
            ToolResult : 执行结果，永不抛出异常
        """
        try:
            result = self._run(**kwargs)
            if isinstance(result, str):
                content = result
            else:
                content = json.dumps(result, ensure_ascii=False, default=str)
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                content=content,
                success=True,
            )
        except Exception as exc:
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                content="",
                success=False,
                error=str(exc),
            )

    def definition(self) -> ToolDefinition:
        """构造 ToolDefinition（用于注册到 ToolRegistry）。"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema,
        )

    def __repr__(self) -> str:
        return f"<Tool:{self.name}>"
