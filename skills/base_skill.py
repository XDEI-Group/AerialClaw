"""
base_skill.py
技能抽象基类，所有技能必须继承此类。

技能分类：
    skill_type = "hard"        硬技能：与具体硬件绑定的原子能力，不可学习，直接调用机器人 API
                               接口格式统一，但底层实现由硬件厂商/驱动决定
    skill_type = "soft"        软技能：可进化的组合能力，由多个技能组合而成，LLM 可生成/更新
    skill_type = "perception"  感知技能：传感器数据 → 语义信息的转换层

每个技能在注册表中维护：
    last_execution_status  最近一次执行状态（"never" / "success" / "failed"）
    doc_path               skill.md 文档路径（由 LLM 生成后写入）

这两个字段会被打包进技能表（skill catalog），随 system prompt 传给 LLM。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


SkillType = Literal["hard", "soft", "perception"]
ExecutionStatus = Literal["never", "success", "failed"]


@dataclass
class SkillResult:
    """技能单次执行结果"""
    success: bool
    output: dict = field(default_factory=dict)
    error_msg: str = ""
    cost_time: float = 0.0
    logs: list = field(default_factory=list)


class Skill(ABC):
    """
    技能抽象基类。

    类属性（子类必须覆盖）：
        name        : 技能唯一名称，snake_case，例如 "fly_to"
        description : 一句话功能描述，供 LLM 理解用途
        skill_type  : "hard" | "soft" | "perception"
        robot_type  : 适用机器人类型列表，例如 ["UAV"]
        preconditions: 前置条件描述列表，例如 ["battery > 20%"]
        input_schema : 输入参数说明，key=参数名，value=说明字符串
        output_schema: 输出字段说明，key=字段名，value=说明字符串
        cost        : 执行成本估计（抽象单位）

    运行时状态（由 SkillRegistry 维护，不需要子类设置）：
        last_execution_status : 最近一次执行状态
        doc_path              : skill.md 的文件路径，生成后自动写入
    """

    # ── 子类必须覆盖的类属性 ─────────────────────────────────────────────────
    name: str = ""
    description: str = ""
    skill_type: SkillType = "soft"
    robot_type: list = []
    preconditions: list = []
    input_schema: dict = {}    # 例如 {"target_position": "[x,y,z] 目标三维坐标"}
    output_schema: dict = {}   # 例如 {"arrived_position": "[x,y,z] 实际到达坐标"}
    cost: float = 1.0

    # ── 运行时状态（由 SkillRegistry 注入，子类不用管）──────────────────────
    last_execution_status: ExecutionStatus = "never"
    doc_path: str = ""         # 例如 "skills/fly_to/skill.md"

    # ── 必须实现的方法 ───────────────────────────────────────────────────────

    def check_precondition(self, robot_state: dict) -> bool:
        """
        检查前置条件是否满足。
        硬技能子类应覆盖此方法做真实检查；软技能默认返回 True。

        Args:
            robot_state: 机器人当前状态字典（来自 WorldModel）

        Returns:
            bool
        """
        return True

    @abstractmethod
    def execute(self, input_data: dict) -> SkillResult:
        """
        执行技能。

        Args:
            input_data: 技能执行参数，结构由 input_schema 描述

        Returns:
            SkillResult
        """
        pass

    # ── 公共辅助方法 ─────────────────────────────────────────────────────────

    def get_cost(self) -> float:
        return self.cost

    def get_metadata(self) -> dict:
        """
        返回完整元信息，用于 skill_doc_generator 生成 skill.md。

        Returns:
            dict: name/description/skill_type/robot_type/preconditions/
                  input_schema/output_schema/cost/last_execution_status/doc_path
        """
        return {
            "name": self.name,
            "description": self.description,
            "skill_type": self.skill_type,
            "robot_type": self.robot_type,
            "preconditions": self.preconditions,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "cost": self.cost,
            "last_execution_status": self.last_execution_status,
            "doc_path": self.doc_path,
        }

    def get_catalog_entry(self) -> dict:
        """
        返回精简的技能表条目，供 SkillRegistry 打包进 system prompt。
        只含 LLM 决策所需的最小信息，避免 context 过长。

        Returns:
            dict: name/description/skill_type/robot_type/input_schema/
                  output_schema/last_execution_status/doc_path
        """
        return {
            "name": self.name,
            "description": self.description,
            "skill_type": self.skill_type,
            "robot_type": self.robot_type,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "last_execution_status": self.last_execution_status,
            "doc_path": self.doc_path,
        }

    def __repr__(self):
        return (
            f"<Skill name={self.name} type={self.skill_type} "
            f"status={self.last_execution_status}>"
        )
