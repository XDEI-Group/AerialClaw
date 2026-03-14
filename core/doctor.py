"""
core/doctor.py — AerialClaw 系统健康检查框架

用法：
    命令行: python -m core.doctor
    代码:   Doctor().run()
    API:    GET /api/doctor/run
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """单项检查结果"""
    name: str
    category: str
    status: Literal["ok", "warn", "fail"]
    message: str
    fix_hint: str = ""
    duration_ms: float = 0

    @property
    def icon(self) -> str:
        return {"ok": "✅", "warn": "⚠️", "fail": "❌"}[self.status]

    @property
    def score(self) -> int:
        return {"ok": 10, "warn": 5, "fail": 0}[self.status]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "message": self.message,
            "fix_hint": self.fix_hint,
            "duration_ms": round(self.duration_ms, 1),
        }


class HealthCheck(ABC):
    """健康检查基类，所有检查项继承它"""
    name: str = "unnamed"
    category: str = "general"

    @abstractmethod
    def check(self) -> CheckResult:
        """执行检查，返回结果"""
        ...

    def _ok(self, msg: str) -> CheckResult:
        return CheckResult(self.name, self.category, "ok", msg)

    def _warn(self, msg: str, fix: str = "") -> CheckResult:
        return CheckResult(self.name, self.category, "warn", msg, fix)

    def _fail(self, msg: str, fix: str = "") -> CheckResult:
        return CheckResult(self.name, self.category, "fail", msg, fix)


@dataclass
class HealthReport:
    """完整健康报告"""
    timestamp: str = ""
    results: list[CheckResult] = field(default_factory=list)
    duration_ms: float = 0

    @property
    def score(self) -> int:
        if not self.results:
            return 0
        total = sum(r.score for r in self.results)
        max_score = len(self.results) * 10
        return round(total / max_score * 100)

    @property
    def grade(self) -> str:
        s = self.score
        if s >= 90: return "A"
        if s >= 70: return "B"
        if s >= 50: return "C"
        return "D"

    @property
    def grade_color(self) -> str:
        return {"A": "green", "B": "yellow", "C": "orange", "D": "red"}.get(self.grade, "red")

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "score": self.score,
            "grade": self.grade,
            "duration_ms": round(self.duration_ms, 1),
            "results": [r.to_dict() for r in self.results],
            "summary": self._summary(),
        }

    def _summary(self) -> str:
        ok = sum(1 for r in self.results if r.status == "ok")
        warn = sum(1 for r in self.results if r.status == "warn")
        fail = sum(1 for r in self.results if r.status == "fail")
        return f"{ok}✅ {warn}⚠️ {fail}❌ / {len(self.results)} 项 | 健康分: {self.score}/100 ({self.grade})"

    def __str__(self) -> str:
        lines = [
            "",
            "🏥 AerialClaw 健康检查报告",
            f"   时间: {self.timestamp}",
            "─" * 50,
        ]
        # 按类别分组
        categories = {}
        for r in self.results:
            categories.setdefault(r.category, []).append(r)

        cat_labels = {
            "connection": "🔌 连接状态",
            "sensor": "🎯 传感器健康",
            "ai": "🧠 AI 系统",
            "config": "📋 配置审计",
        }
        for cat, checks in categories.items():
            lines.append(f"\n  {cat_labels.get(cat, cat)}")
            for r in checks:
                line = f"    {r.icon} {r.name}: {r.message}"
                if r.fix_hint and r.status != "ok":
                    line += f"\n       → {r.fix_hint}"
                lines.append(line)

        lines.append("\n" + "─" * 50)
        lines.append(f"  {self._summary()}")
        lines.append(f"  耗时: {self.duration_ms:.0f}ms")
        lines.append("")
        return "\n".join(lines)


class Doctor:
    """系统健康检查器"""

    def __init__(self):
        self._checks: list[HealthCheck] = []

    def register(self, check: HealthCheck) -> "Doctor":
        """注册检查项"""
        self._checks.append(check)
        return self

    def run(self) -> HealthReport:
        """执行所有检查"""
        report = HealthReport(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        start = time.time()

        for check in self._checks:
            t0 = time.time()
            try:
                result = check.check()
            except Exception as e:
                result = CheckResult(
                    check.name, check.category, "fail",
                    f"检查异常: {str(e)[:100]}"
                )
            result.duration_ms = (time.time() - t0) * 1000
            report.results.append(result)

        report.duration_ms = (time.time() - start) * 1000
        return report


def create_doctor() -> Doctor:
    """创建预注册全部检查项的 Doctor 实例"""
    from core.doctor_checks.connection import (
        LLMConnectionCheck, VLMConnectionCheck, MAVSDKCheck, PX4Check
    )
    from core.doctor_checks.sensor import (
        CameraCheck, LidarCheck, BatteryCheck
    )
    from core.doctor_checks.ai import (
        PlannerCheck, ReflectionCheck, SkillStatsCheck
    )
    from core.doctor_checks.config import (
        EnvConfigCheck, SkillDocsCheck, ProfileCheck, DiskSpaceCheck
    )

    doctor = Doctor()
    # 连接
    doctor.register(LLMConnectionCheck())
    doctor.register(VLMConnectionCheck())
    doctor.register(MAVSDKCheck())
    doctor.register(PX4Check())
    # 传感器
    doctor.register(CameraCheck())
    doctor.register(LidarCheck())
    doctor.register(BatteryCheck())
    # AI
    doctor.register(PlannerCheck())
    doctor.register(ReflectionCheck())
    doctor.register(SkillStatsCheck())
    # 配置
    doctor.register(EnvConfigCheck())
    doctor.register(SkillDocsCheck())
    doctor.register(ProfileCheck())
    doctor.register(DiskSpaceCheck())

    return doctor


if __name__ == "__main__":
    doc = create_doctor()
    report = doc.run()
    print(report)
