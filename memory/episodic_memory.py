"""
episodic_memory.py
情节记忆模块：存储与检索历史任务经验。

职责：
    - 存储每次任务的执行经历（任务描述、环境、结果、成功率）
    - 提供按任务相似度检索历史经验的接口
    - 减少 Brain 模块的重复推理成本

Functions:
    store_episode(episode)      - 存储一条任务经历
    retrieve_episode(query)     - 按关键词检索相关历史经历

数据格式（episode）：
    {
        "episode_id": str,
        "task": str,
        "environment": str,
        "skills_used": list,
        "robot": str,
        "success": bool,
        "reward": float,
        "cost_time": float,
        "timestamp": float
    }
"""

import time
import uuid
from typing import Optional


class EpisodicMemory:
    """
    情节记忆。
    以列表结构维护任务经历，支持关键词匹配检索。

    未来升级方向：
        - 向量化 episode embedding + 语义检索（RAG）
        - 按环境条件、成功率加权排序
    """

    def __init__(self):
        # 内存存储，key 为 episode_id
        self._store: dict[str, dict] = {}

    def store_episode(self, episode: dict) -> str:
        """
        存储一条任务经历。

        Args:
            episode: 任务经历字典，至少包含 task、environment、success 字段。
                     若不含 episode_id，自动生成。

        Returns:
            str: 存储的 episode_id
        """
        if "episode_id" not in episode or not episode["episode_id"]:
            episode["episode_id"] = str(uuid.uuid4())
        if "timestamp" not in episode:
            episode["timestamp"] = time.time()

        self._store[episode["episode_id"]] = episode
        return episode["episode_id"]

    def retrieve_episode(
        self,
        query: str,
        top_k: int = 3,
        success_only: bool = False,
    ) -> list[dict]:
        """
        按关键词检索相关历史经历。

        匹配规则：query 中的任意词出现在 episode.task 或 episode.environment 中即命中。
        结果按成功率降序、时间戳降序排列。

        Args:
            query:       查询字符串（自然语言任务描述）
            top_k:       最多返回条数，默认 3
            success_only: 若为 True，只返回成功的经历

        Returns:
            list[dict]: 最相关的历史经历列表
        """
        query_tokens = set(query.lower().split())
        results = []

        for ep in self._store.values():
            if success_only and not ep.get("success", False):
                continue

            task_text = ep.get("task", "").lower()
            env_text = ep.get("environment", "").lower()
            combined = task_text + " " + env_text

            # 简单词汇重叠评分
            score = sum(1 for token in query_tokens if token in combined)
            if score > 0:
                results.append((score, ep))

        # 按得分降序，再按时间戳降序
        results.sort(key=lambda x: (x[0], x[1].get("timestamp", 0)), reverse=True)
        return [ep for _, ep in results[:top_k]]

    def get_all_episodes(self) -> list[dict]:
        """
        返回所有存储的历史经历。

        Returns:
            list[dict]
        """
        return list(self._store.values())

    def get_success_rate(self, task_keyword: str) -> float:
        """
        计算包含指定关键词的任务的历史成功率。

        Args:
            task_keyword: 任务关键词

        Returns:
            float: 成功率 [0.0, 1.0]，无相关记录返回 -1.0
        """
        related = [
            ep for ep in self._store.values()
            if task_keyword.lower() in ep.get("task", "").lower()
        ]
        if not related:
            return -1.0
        success_count = sum(1 for ep in related if ep.get("success", False))
        return round(success_count / len(related), 4)

    def clear(self) -> None:
        """清空所有历史经历。"""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    def __repr__(self):
        return f"<EpisodicMemory episodes={len(self._store)}>"
