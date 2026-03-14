"""
memory/memory_manager.py — AerialClaw 四层记忆管理器

层级：
  working  — 工作记忆，当前任务上下文（滑动窗口，纯内存）
  episodic — 情景记忆，任务执行经历（向量存储）
  skill    — 技能记忆，技能执行统计与经验（向量存储）
  world    — 世界知识，环境发现、地标、规律（向量存储）
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from core.errors import MemoryRetrievalError, MemoryStoreError
from core.logger import get_logger
from memory.vector_store import VectorStore, MemoryItem

logger = get_logger("memory.memory_manager")


# ── 工作记忆 ─────────────────────────────────────────────────

class WorkingMemory:
    """
    工作记忆：当前任务上下文，滑动窗口（先进先出）。

    线程安全；不持久化（任务结束即清空）。
    """

    def __init__(self, max_items: int = 20):
        self._max = max_items
        self._items: deque[str] = deque(maxlen=max_items)
        self._lock = threading.Lock()

    def add(self, item: str) -> None:
        """添加一条上下文条目（超出窗口自动丢弃最旧条目）。"""
        with self._lock:
            self._items.append(item)

    def get_recent(self, n: int = 10) -> List[str]:
        """返回最近 n 条记录（n=0 返回全部）。"""
        with self._lock:
            items = list(self._items)
        return items[-n:] if n > 0 else items

    def clear(self) -> None:
        """清空工作记忆（任务结束时调用）。"""
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


# ── 四层记忆管理器 ────────────────────────────────────────────

class MemoryManager:
    """
    四层记忆管理器。

    - working:  当前任务上下文，滑动窗口
    - episodic: 任务执行经历（情景记忆）
    - skill:    技能执行统计与经验
    - world:    世界知识（环境发现、地标等）
    """

    def __init__(self):
        self.working = WorkingMemory()
        self.episodic = VectorStore("episodic")
        self.skill = VectorStore("skill")
        self.world = VectorStore("world")
        self._lock = threading.Lock()
        logger.info("MemoryManager 初始化完成（4层记忆）")

    # ── 检索 ──────────────────────────────────────────────────

    def recall(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """
        跨层检索相关记忆，合并去重，按相关度排序。

        搜索 episodic、skill、world 三个向量层；working 记忆以
        get_recent() 方式单独提供，不参与语义排序。

        Args:
            query: 查询语句
            top_k: 每层返回条目数上限（总数 ≤ top_k * 3）

        Returns:
            去重后按 score 降序排列的 MemoryItem 列表

        Raises:
            MemoryRetrievalError: 检索失败时
        """
        try:
            seen_ids: set[str] = set()
            merged: List[MemoryItem] = []

            for store_name, store in [
                ("episodic", self.episodic),
                ("skill", self.skill),
                ("world", self.world),
            ]:
                try:
                    items = store.search(query, top_k)
                except Exception as e:
                    logger.warning(f"[recall] {store_name} 检索失败：{e}")
                    continue

                for item in items:
                    if item.memory_id not in seen_ids:
                        seen_ids.add(item.memory_id)
                        merged.append(item)

            merged.sort(key=lambda x: x.score, reverse=True)
            logger.debug(f"[recall] query='{query[:30]}…' 共检索到 {len(merged)} 条")
            return merged

        except Exception as e:
            raise MemoryRetrievalError(
                f"跨层记忆检索失败：{e}",
                fix_hint="确认各向量存储已正常初始化",
            ) from e

    # ── 写入 ──────────────────────────────────────────────────

    def store_episode(self, task_log: Dict[str, Any]) -> str:
        """
        存储任务执行经历到情景记忆。

        Args:
            task_log: 任务日志字典，应包含 task、result、duration 等字段

        Returns:
            memory_id

        Raises:
            MemoryStoreError: 存储失败时
        """
        try:
            task = task_log.get("task", "unknown")
            result = task_log.get("result", "unknown")
            duration = task_log.get("duration", 0)
            summary = (
                f"任务：{task} | 结果：{result} | 耗时：{duration:.1f}s"
            )
            metadata = {
                "type": "episode",
                "timestamp": time.time(),
                **{k: str(v) for k, v in task_log.items()},
            }
            mid = self.episodic.add(summary, metadata)
            self.working.add(f"[episode] {summary}")
            logger.info(f"[store_episode] 已记录任务经历：{summary[:60]}")
            return mid
        except Exception as e:
            raise MemoryStoreError(
                f"情景记忆存储失败：{e}",
                fix_hint="检查向量存储状态",
            ) from e

    def update_skill_stats(
        self, skill: str, success: bool, cost_time: float
    ) -> str:
        """
        更新技能执行统计到技能记忆。

        Args:
            skill:     技能名称
            success:   是否成功
            cost_time: 执行耗时（秒）

        Returns:
            memory_id

        Raises:
            MemoryStoreError: 存储失败时
        """
        try:
            status = "成功" if success else "失败"
            text = f"技能 {skill} 执行{status}，耗时 {cost_time:.2f}s"
            metadata = {
                "type": "skill_stat",
                "skill": skill,
                "success": success,
                "cost_time": cost_time,
                "timestamp": time.time(),
            }
            mid = self.skill.add(text, metadata)
            logger.debug(f"[update_skill_stats] {text}")
            return mid
        except Exception as e:
            raise MemoryStoreError(f"技能统计存储失败：{e}") from e

    def store_world_knowledge(self, knowledge: str, source: str) -> str:
        """
        存储世界知识（环境发现、地标、规律等）。

        Args:
            knowledge: 知识内容
            source:    知识来源（设备名、传感器等）

        Returns:
            memory_id

        Raises:
            MemoryStoreError: 存储失败时
        """
        try:
            metadata = {
                "type": "world",
                "source": source,
                "timestamp": time.time(),
            }
            mid = self.world.add(knowledge, metadata)
            logger.info(f"[store_world] [{source}] {knowledge[:60]}")
            return mid
        except Exception as e:
            raise MemoryStoreError(f"世界知识存储失败：{e}") from e

    # ── 维护 ──────────────────────────────────────────────────

    def consolidate(self) -> None:
        """
        定期记忆整理：记录当前各层统计，预留去重/衰减扩展点。

        当前实现：打印统计摘要；后续可扩展相似度去重、
        低分条目衰减删除等策略。
        """
        with self._lock:
            stats = {
                "working": len(self.working),
                "episodic": self.episodic.count(),
                "skill": self.skill.count(),
                "world": self.world.count(),
            }
            logger.info(f"[consolidate] 记忆统计：{stats}")
            # TODO: 可在此扩展相似度去重、时间衰减删除逻辑

    # ── 规划支持 ──────────────────────────────────────────────

    def get_context_for_planning(self, task: str) -> str:
        """
        为 Brain 规划提供精炼的记忆上下文。

        整合工作记忆最近条目 + 跨层语义检索结果，
        格式化为可直接注入 prompt 的字符串。

        Args:
            task: 当前规划任务描述

        Returns:
            格式化的记忆上下文字符串
        """
        lines: List[str] = ["## 记忆上下文\n"]

        # 工作记忆（最近 5 条）
        recent = self.working.get_recent(5)
        if recent:
            lines.append("### 当前上下文（工作记忆）")
            lines.extend(f"- {item}" for item in recent)
            lines.append("")

        # 语义检索（top 5）
        try:
            recalled = self.recall(task, top_k=5)
            if recalled:
                lines.append("### 相关历史记忆")
                for item in recalled:
                    tag = item.metadata.get("type", "?")
                    lines.append(f"- [{tag}] {item.text}  (score={item.score:.2f})")
                lines.append("")
        except MemoryRetrievalError as e:
            logger.warning(f"[get_context_for_planning] 检索失败：{e}")

        return "\n".join(lines)
