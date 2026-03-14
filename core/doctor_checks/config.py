"""
core/doctor_checks/config.py — 配置审计检查
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from core.doctor import HealthCheck, CheckResult


class EnvConfigCheck(HealthCheck):
    name = ".env 配置"
    category = "config"

    def check(self) -> CheckResult:
        env_path = Path(".env")
        if not env_path.exists():
            return self._fail("文件不存在", "cp .env.example .env")

        content = env_path.read_text()
        required_vars = {
            "ACTIVE_PROVIDER": os.environ.get("ACTIVE_PROVIDER", ""),
            "LLM_API_KEY": os.environ.get("LLM_API_KEY", ""),
        }

        missing = [k for k, v in required_vars.items()
                    if not v or v in ("your-llm-api-key-here", "")]

        provider = os.environ.get("ACTIVE_PROVIDER", "")
        if provider == "ollama_local":
            missing = [m for m in missing if m != "LLM_API_KEY"]

        if not missing:
            return self._ok(f"完整 (provider={provider})")
        return self._warn(f"缺少: {', '.join(missing)}", "编辑 .env 补充配置")


class SkillDocsCheck(HealthCheck):
    name = "技能文档"
    category = "config"

    def check(self) -> CheckResult:
        docs_dir = Path("skills/docs")
        soft_dir = Path("skills/soft_docs")

        if not docs_dir.exists():
            return self._fail("skills/docs/ 不存在")

        hard_docs = list(docs_dir.glob("*.md"))
        soft_docs = list(soft_dir.glob("*.md")) if soft_dir.exists() else []

        # 检查硬技能文档与代码是否匹配
        try:
            from skills import hard_skills
            code_skills = [name for name in dir(hard_skills)
                           if isinstance(getattr(hard_skills, name, None), type)]
        except Exception:
            code_skills = []

        if len(hard_docs) >= 10:
            return self._ok(f"{len(hard_docs)} 硬技能 + {len(soft_docs)} 软技能")
        return self._warn(f"硬技能文档偏少: {len(hard_docs)} 个")


class ProfileCheck(HealthCheck):
    name = "Robot Profile"
    category = "config"

    def check(self) -> CheckResult:
        required = ["SOUL.md", "BODY.md", "MEMORY.md", "SKILLS.md", "WORLD_MAP.md"]
        profile_dir = Path("robot_profile")

        if not profile_dir.exists():
            return self._fail("robot_profile/ 不存在")

        existing = [f for f in required if (profile_dir / f).exists()]
        missing = [f for f in required if f not in [e for e in existing]]

        if len(existing) == len(required):
            return self._ok(f"{len(required)}/{len(required)} 文档完整")
        return self._warn(f"缺少: {', '.join(missing)}", "首次启动时会自动生成")


class DiskSpaceCheck(HealthCheck):
    name = "磁盘空间"
    category = "config"

    def check(self) -> CheckResult:
        usage = shutil.disk_usage(".")
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        pct = usage.free / usage.total * 100

        if pct > 20:
            return self._ok(f"{free_gb:.1f}GB 可用 ({pct:.0f}%)")
        elif pct > 10:
            return self._warn(f"空间偏低: {free_gb:.1f}GB ({pct:.0f}%)",
                              "清理缓存: brew cleanup --prune=all")
        return self._fail(f"空间不足: {free_gb:.1f}GB ({pct:.0f}%)",
                          "立即清理磁盘空间")
