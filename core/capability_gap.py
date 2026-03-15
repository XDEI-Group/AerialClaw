"""
core/capability_gap.py — 能力缺口检测

在规划阶段检测计划中引用的技能是否存在，
区分"软件可补的缺口"和"硬件不可能的缺口"。

三层防线：
  1. 软技能写入时校验 — 引用了不存在的硬技能则警告
  2. 规划时拦截 — 计划中的技能不存在则阻止执行
  3. 缺口分析 — 判断缺口能否通过代码生成自动填补
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GapAnalysis:
    """能力缺口分析结果"""
    skill_name: str
    exists: bool
    gap_type: str = ""          # none / software / hardware / unknown
    reason: str = ""
    auto_fillable: bool = False  # 能否通过代码生成自动填补
    suggestion: str = ""


@dataclass
class PlanValidation:
    """计划校验结果"""
    valid: bool
    gaps: List[GapAnalysis] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# 已知的硬件依赖能力 — 这些需要物理硬件，代码无法填补
_HARDWARE_CAPABILITIES = frozenset([
    "fly", "drive", "grab", "lift", "push", "pull",
    "camera_physical", "lidar_physical", "arm_physical",
    "speaker_physical", "microphone_physical",
    "gps_hardware", "imu_hardware", "barometer_hardware",
])

# 已知的软件可实现能力 — 可以通过代码生成填补
_SOFTWARE_CAPABILITIES = frozenset([
    "http_request", "web_search", "file_read", "file_write",
    "json_parse", "math_compute", "text_process",
    "image_process", "data_convert", "timer", "scheduler",
    "notification", "log_write", "api_call",
])


class CapabilityGapDetector:
    """
    能力缺口检测器。

    在规划执行前检测计划是否可行，
    提供缺口分析和自动填补建议。
    """

    def __init__(self, skill_registry=None) -> None:
        self._registry = skill_registry

    def set_registry(self, registry) -> None:
        """设置技能注册表"""
        self._registry = registry

    # ── 第一层：软技能文档校验 ────────────────────────────────

    def validate_soft_skill(self, doc_content: str, available_skills: Set[str]) -> List[str]:
        """
        校验软技能文档中引用的技能是否存在。

        Args:
            doc_content: 软技能 Markdown 文档内容
            available_skills: 当前注册的技能名称集合

        Returns:
            warnings: 警告信息列表
        """
        warnings = []
        # 从文档中提取可能的技能引用（反引号中的名称）
        import re
        refs = set(re.findall(r'`(\w+)`', doc_content))

        # 常见的非技能关键词，过滤掉
        non_skills = {
            'true', 'false', 'none', 'null', 'json', 'python',
            'step', 'plan', 'task', 'robot', 'parameters',
            'str', 'int', 'float', 'bool', 'list', 'dict',
        }
        refs = {r for r in refs if r.lower() not in non_skills and len(r) > 2}

        for ref in refs:
            if ref not in available_skills:
                # 检查是否可能是技能名
                if '_' in ref or ref.islower():
                    warnings.append(
                        f"软技能文档引用了 `{ref}`，但当前技能表中不存在该技能"
                    )

        return warnings

    # ── 第二层：计划校验 ─────────────────────────────────────

    def validate_plan(self, steps: List[Dict[str, Any]]) -> PlanValidation:
        """
        校验执行计划中所有技能是否可用。

        Args:
            steps: 计划步骤列表

        Returns:
            PlanValidation: 校验结果
        """
        if self._registry is None:
            return PlanValidation(valid=True, warnings=["技能注册表未设置，跳过校验"])

        available = set()
        catalog = self._registry.get_skill_catalog()
        for s in catalog:
            available.add(s.get("name", ""))

        gaps = []
        for step in steps:
            skill_name = step.get("skill", "")
            if not skill_name:
                continue
            if skill_name not in available:
                gap = self.analyze_gap(skill_name)
                gaps.append(gap)

        valid = len(gaps) == 0
        return PlanValidation(valid=valid, gaps=gaps)

    # ── 第三层：缺口分析 ─────────────────────────────────────

    def analyze_gap(self, skill_name: str) -> GapAnalysis:
        """
        分析单个技能缺口的性质。

        判断逻辑：
        - 如果技能名暗示需要物理硬件 → hardware 缺口，不可自动填补
        - 如果技能名暗示纯软件操作 → software 缺口，可尝试代码生成
        - 无法判断 → unknown

        Args:
            skill_name: 不存在的技能名称

        Returns:
            GapAnalysis: 缺口分析结果
        """
        name_lower = skill_name.lower()

        # 检查是否暗示硬件依赖
        hardware_hints = [
            "grab", "grip", "lift", "push", "pull", "arm_",
            "wheel", "motor", "servo", "actuator",
            "physical", "_hardware",
        ]
        for hint in hardware_hints:
            if hint in name_lower:
                return GapAnalysis(
                    skill_name=skill_name,
                    exists=False,
                    gap_type="hardware",
                    reason=f"技能 '{skill_name}' 需要物理硬件支持，无法通过软件实现",
                    auto_fillable=False,
                    suggestion="该操作需要对应的物理执行器，当前设备不具备此能力",
                )

        # 检查是否是纯软件操作
        software_hints = [
            "search", "query", "parse", "compute", "calculate",
            "convert", "format", "download", "upload", "request",
            "read_file", "write_file", "http", "api", "web",
            "process", "analyze", "generate", "translate",
        ]
        for hint in software_hints:
            if hint in name_lower:
                return GapAnalysis(
                    skill_name=skill_name,
                    exists=False,
                    gap_type="software",
                    reason=f"技能 '{skill_name}' 是纯软件操作，可通过代码生成实现",
                    auto_fillable=True,
                    suggestion=f"可尝试使用 CodeGenerator 自动生成 '{skill_name}' 的实现",
                )

        # 无法确定
        return GapAnalysis(
            skill_name=skill_name,
            exists=False,
            gap_type="unknown",
            reason=f"无法判断技能 '{skill_name}' 的缺口类型",
            auto_fillable=False,
            suggestion="请检查该技能是否需要特定硬件或可以通过软件实现",
        )

    def get_available_skills(self) -> Set[str]:
        """获取当前所有可用技能名称"""
        if self._registry is None:
            return set()
        return {s.get("name", "") for s in self._registry.get_skill_catalog()}
