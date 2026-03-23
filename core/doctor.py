"""
core/doctor.py — HealthCheck 基类（保留给 doctor_checks/ 使用）

注意：完整的 Doctor Agent 已迁移到 doctor/agent.py。
此文件仅保留 HealthCheck 和 CheckResult 基类供 doctor_checks/ 检查项导入。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


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
    """健康检查基类"""
    name: str = "unnamed"
    category: str = "general"

    @abstractmethod
    def check(self) -> CheckResult:
        ...

    def _ok(self, msg: str) -> CheckResult:
        return CheckResult(self.name, self.category, "ok", msg)

    def _warn(self, msg: str, fix: str = "") -> CheckResult:
        return CheckResult(self.name, self.category, "warn", msg, fix)

    def _fail(self, msg: str, fix: str = "") -> CheckResult:
        return CheckResult(self.name, self.category, "fail", msg, fix)
