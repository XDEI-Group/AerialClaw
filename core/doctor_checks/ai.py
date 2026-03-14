"""
core/doctor_checks/ai.py — AI 系统诊断
"""

from __future__ import annotations

from pathlib import Path
from core.doctor import HealthCheck, CheckResult


class PlannerCheck(HealthCheck):
    name = "规划系统"
    category = "ai"

    def check(self) -> CheckResult:
        try:
            from memory.task_log import TaskLogger
            tl = TaskLogger.get_instance()
            if tl is None:
                return self._warn("TaskLogger 未初始化")

            logs = tl.get_recent(limit=10)
            if not logs:
                return self._ok("就绪（无历史任务）")

            success = sum(1 for l in logs if l.get("success"))
            total = len(logs)
            rate = success / total * 100
            if rate >= 80:
                return self._ok(f"近 {total} 次任务成功率: {rate:.0f}%")
            elif rate >= 50:
                return self._warn(f"成功率偏低: {rate:.0f}% ({success}/{total})")
            return self._fail(f"成功率过低: {rate:.0f}% ({success}/{total})",
                              "检查 LLM 模型能力或调整 prompt")
        except Exception:
            return self._ok("就绪（TaskLogger 未加载）")


class ReflectionCheck(HealthCheck):
    name = "反思引擎"
    category = "ai"

    def check(self) -> CheckResult:
        memory_path = Path("robot_profile/MEMORY.md")
        if not memory_path.exists():
            return self._warn("MEMORY.md 不存在", "首次任务执行后会自动创建")

        content = memory_path.read_text(encoding="utf-8")
        lines = len(content.strip().splitlines())
        size_kb = len(content.encode()) / 1024

        if size_kb > 100:
            return self._warn(f"MEMORY.md 过大 ({size_kb:.0f}KB, {lines} 行)",
                              "建议清理过时记忆")
        if lines > 5:
            return self._ok(f"活跃 ({lines} 行, {size_kb:.1f}KB)")
        return self._ok(f"已初始化 ({lines} 行)")


class SkillStatsCheck(HealthCheck):
    name = "技能统计"
    category = "ai"

    def check(self) -> CheckResult:
        skills_path = Path("robot_profile/SKILLS.md")
        if not skills_path.exists():
            return self._warn("SKILLS.md 不存在")

        content = skills_path.read_text(encoding="utf-8")

        # 统计技能数量
        hard_count = content.lower().count("hard")
        soft_count = content.lower().count("soft")

        # 检查技能文档完整性
        docs = list(Path("skills/docs").glob("*.md"))
        soft_docs = list(Path("skills/soft_docs").glob("*.md"))

        return self._ok(f"{len(docs)} 硬技能文档 + {len(soft_docs)} 软技能文档")
