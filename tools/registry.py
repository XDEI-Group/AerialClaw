"""
tools/registry.py  —— 工具注册表

职责：
    - 统一管理所有已注册的 BaseTool 实例
    - 向 LLM 提供 OpenAI Function Calling 格式的工具列表
    - 按名称路由到具体 Tool 实例

用法：
    registry = ToolRegistry()
    registry.register(GetRobotStatusTool(world_model))
    registry.register(RetrieveEpisodeTool(episodic_memory))

    # 传给 chat_with_tools()
    tool_defs = registry.get_tool_definitions()

    # ToolExecutor 内部按名称取工具
    tool = registry.get("get_robot_status")
"""

from __future__ import annotations

from typing import Iterator

from tools.base_tool import BaseTool, ToolDefinition


class ToolRegistry:
    """
    工具注册表。

    线程不安全（单线程规划场景下足够）。
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    # ── 注册 ─────────────────────────────────────────────────────────────────

    def register(self, tool: BaseTool) -> None:
        """
        注册一个工具实例。

        Args:
            tool: BaseTool 子类实例

        Raises:
            ValueError: 工具名称重复时
        """
        if tool.name in self._tools:
            raise ValueError(
                f"[ToolRegistry] 工具 '{tool.name}' 已注册，"
                f"请先调用 unregister() 或使用 register(overwrite=True)"
            )
        self._tools[tool.name] = tool

    def register_overwrite(self, tool: BaseTool) -> None:
        """注册工具，允许覆盖同名工具。"""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """
        注销工具。

        Args:
            name: 工具名称

        Raises:
            KeyError: 工具不存在时
        """
        if name not in self._tools:
            raise KeyError(f"[ToolRegistry] 工具 '{name}' 未注册")
        del self._tools[name]

    # ── 查询 ─────────────────────────────────────────────────────────────────

    def get(self, name: str) -> BaseTool:
        """
        按名称获取工具实例。

        Args:
            name: 工具名称

        Returns:
            BaseTool 实例

        Raises:
            KeyError: 工具不存在时
        """
        if name not in self._tools:
            raise KeyError(
                f"[ToolRegistry] 未知工具 '{name}'，"
                f"已注册：{list(self._tools.keys())}"
            )
        return self._tools[name]

    def has(self, name: str) -> bool:
        """检查工具是否已注册。"""
        return name in self._tools

    def all_tools(self) -> list[BaseTool]:
        """返回所有已注册工具的列表。"""
        return list(self._tools.values())

    # ── LLM 接口 ─────────────────────────────────────────────────────────────

    def get_tool_definitions(self) -> list[dict]:
        """
        返回 OpenAI Function Calling 格式的工具定义列表。

        直接传给 chat_with_tools() 的 tools 参数：

            client.chat_with_tools(messages, tools=registry.get_tool_definitions())

        Returns:
            list[dict]: OpenAI tools 格式列表
        """
        return [tool.definition().to_openai_format() for tool in self._tools.values()]

    def get_definitions(self) -> list[ToolDefinition]:
        """返回 ToolDefinition 对象列表（非 OpenAI 格式）。"""
        return [tool.definition() for tool in self._tools.values()]

    # ── 迭代 ─────────────────────────────────────────────────────────────────

    def __iter__(self) -> Iterator[BaseTool]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        names = list(self._tools.keys())
        return f"<ToolRegistry tools={names}>"
