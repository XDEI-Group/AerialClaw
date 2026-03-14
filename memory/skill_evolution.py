"""
skill_evolution.py
技能进化模块: 基于历史反思数据, 检测技能的长期趋势并提出优化建议。

功能:
    - 跟踪技能表现的时间序列(成功率、耗时的变化趋势)
    - 检测表现退化(degradation): 连续失败或成功率下降
    - 检测参数漂移: 推荐参数多次被反思修改
    - 生成进化报告: 哪些技能需要关注, 哪些参数应该固化

设计思路:
    反思引擎每次产出 skill_feedback -> 追加到 evolution_log
    定期(或手动)调用 analyze() 生成进化报告

数据流:
    ReflectionEngine.reflect() -> skill_feedback
        -> SkillEvolution.record_feedback()
        -> SkillEvolution.analyze() -> 进化报告
"""

import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

EVOLUTION_LOG_DIR = Path(__file__).parent.parent / "data" / "skill_evolution"


class SkillEvolution:
    """
    技能进化跟踪器。

    记录每次反思对技能的评价, 并分析长期趋势。

    用法:
        evo = SkillEvolution()
        evo.record_feedback(reflection)          # 每次反思后调用
        report = evo.analyze()                   # 需要时生成报告
        degraded = evo.get_degraded_skills()     # 获取退化技能列表
    """

    def __init__(self, persist: bool = True):
        """
        Args:
            persist: 是否持久化到磁盘。True 时数据写入 data/skill_evolution/
        """
        self._persist = persist
        # {skill_name: [{"timestamp": float, "performance": str, "suggestion": str, ...}]}
        self._history = defaultdict(list)

        if persist:
            EVOLUTION_LOG_DIR.mkdir(parents=True, exist_ok=True)
            self._load_history()

    def record_feedback(self, reflection: dict) -> None:
        """
        从反思结果中提取技能反馈, 追加到进化历史。

        Args:
            reflection: ReflectionEngine.reflect() 返回的反思 dict
        """
        feedback_list = reflection.get("skill_feedback", [])
        ts = time.time()
        task_summary = reflection.get("summary", "")

        for fb in feedback_list:
            skill_name = fb.get("skill_name", "")
            if not skill_name:
                continue

            record = {
                "timestamp": ts,
                "task": task_summary,
                "performance": fb.get("performance", "unknown"),
                "suggestion": fb.get("suggestion"),
                "recommended_params": fb.get("recommended_params", {}),
            }
            self._history[skill_name].append(record)

        if self._persist and feedback_list:
            self._save_history()

    def get_degraded_skills(self, window: int = 5, threshold: float = 0.4) -> list:
        """
        检测近期表现退化的技能。

        Args:
            window: 检查最近多少次执行
            threshold: poor 比例超过此值视为退化

        Returns:
            list[dict]: [{"skill_name": str, "poor_rate": float, "recent": list}]
        """
        degraded = []
        for skill_name, records in self._history.items():
            recent = records[-window:]
            if len(recent) < 2:
                continue
            poor_count = sum(1 for r in recent if r["performance"] == "poor")
            poor_rate = poor_count / len(recent)
            if poor_rate >= threshold:
                degraded.append({
                    "skill_name": skill_name,
                    "poor_rate": round(poor_rate, 2),
                    "recent_count": len(recent),
                    "last_suggestion": recent[-1].get("suggestion"),
                })
        return degraded

    def get_param_drift(self, skill_name: str) -> list:
        """
        检测某技能的推荐参数是否频繁变化(参数漂移)。

        Returns:
            list[dict]: 参数变化历史 [{"timestamp": float, "params": dict}]
        """
        records = self._history.get(skill_name, [])
        changes = []
        prev_params = None
        for r in records:
            params = r.get("recommended_params", {})
            if params and params != prev_params:
                changes.append({
                    "timestamp": r["timestamp"],
                    "params": params,
                    "task": r.get("task", ""),
                })
                prev_params = params
        return changes

    def analyze(self) -> dict:
        """
        生成技能进化分析报告。

        Returns:
            dict: {
                "timestamp": str,
                "total_skills_tracked": int,
                "total_feedbacks": int,
                "degraded_skills": list,
                "skill_summaries": {skill_name: {good/acceptable/poor 计数, 参数漂移次数}}
            }
        """
        summaries = {}
        total_feedbacks = 0

        for skill_name, records in self._history.items():
            total_feedbacks += len(records)
            perf_counts = {"good": 0, "acceptable": 0, "poor": 0, "unknown": 0}
            for r in records:
                p = r.get("performance", "unknown")
                perf_counts[p] = perf_counts.get(p, 0) + 1

            drift = self.get_param_drift(skill_name)
            summaries[skill_name] = {
                "total_reviews": len(records),
                "performance": perf_counts,
                "param_changes": len(drift),
                "last_review": datetime.fromtimestamp(records[-1]["timestamp"]).strftime("%Y-%m-%d %H:%M") if records else None,
            }

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total_skills_tracked": len(self._history),
            "total_feedbacks": total_feedbacks,
            "degraded_skills": self.get_degraded_skills(),
            "skill_summaries": summaries,
        }

    def _save_history(self):
        """持久化进化历史到 JSON。"""
        path = EVOLUTION_LOG_DIR / "evolution_history.json"
        data = {k: v for k, v in self._history.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_history(self):
        """从磁盘加载进化历史。"""
        path = EVOLUTION_LOG_DIR / "evolution_history.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    self._history[k] = v
                logger.info(f"[SkillEvolution] 加载 {len(self._history)} 个技能的进化历史")
            except Exception as e:
                logger.warning(f"[SkillEvolution] 加载历史失败: {e}")

    def clear(self):
        """清空所有进化历史。"""
        self._history.clear()
        if self._persist:
            path = EVOLUTION_LOG_DIR / "evolution_history.json"
            if path.exists():
                path.unlink()
