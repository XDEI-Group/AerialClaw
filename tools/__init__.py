"""
tools/  —— LLM 工具层

工具（Tool）与技能（Skill）的核心区别：
    - Tool  : LLM 在规划期间主动调用，用于查询实时信息（认知增强）
    - Skill : Runtime 在执行期间被动调用，用于操作物理世界（执行能力）

接口标准：OpenAI Function Calling 格式（tools 参数 + tool_calls 响应）

快速使用：
    from tools import ToolRegistry, ToolExecutor
    from tools.builtin.world_query import GetRobotStatusTool, GetAllRobotsTool, GetTargetsTool
    from tools.builtin.memory_query import RetrieveEpisodeTool, GetSkillReliabilityTool
    from tools.builtin.math_utils import CalculateDistanceTool, FindNearestRobotTool
    from tools.builtin.system_tools import ExecCommandTool

    registry = ToolRegistry()
    registry.register(GetRobotStatusTool(world_model))
    ...

    executor = ToolExecutor(registry)
"""

from tools.base_tool import BaseTool, ToolResult, ToolDefinition
from tools.registry import ToolRegistry
from tools.executor import ToolExecutor
from tools.tool_call_loop import tool_call_loop

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolDefinition",
    "ToolRegistry",
    "ToolExecutor",
    "tool_call_loop",
]
