"""
dynamic_skill_gen.py
软技能动态生成模块: 基于任务执行历史检测重复模式, 自动生成新的软技能文档。

功能:
  6.1 重复模式检测 — 从任务日志中发现重复出现的技能组合
  6.2 generate_skill_doc() — 调用 LLM 生成软技能 SKILL.md
  6.3 淘汰机制 — 清理低使用率/低评分的软技能

设计:
  不是每次任务后都触发, 而是定期(或手动)分析累积日志,
  当某个技能序列重复出现 >= threshold 次时, 提议生成对应的软技能文档。
"""

import json
import logging
import re
from collections import Counter
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ── 6.1 重复模式检测 ────────────────────────────────────────────────────────

def detect_patterns(task_logs: list, min_count: int = 2, min_chain_len: int = 2) -> list:
    """
    从任务日志中检测重复出现的技能链模式。

    Args:
        task_logs: TaskLogger.get_all_logs() 返回的日志列表
        min_count: 最少出现次数, 低于此数不算模式
        min_chain_len: 最短技能链长度

    Returns:
        list[dict]: [
            {
                "pattern": ["takeoff", "fly_to", "hover", "land"],
                "count": 5,
                "avg_duration": 42.3,
                "success_rate": 0.8,
                "task_names": ["搜索区域A", "搜索区域B", ...]
            }
        ]
    """
    # 提取所有技能链
    chains = []
    for log in task_logs:
        trace = log.get("skill_trace", [])
        if len(trace) < min_chain_len:
            continue
        chain = tuple(s.get("skill_name", "?") for s in trace)
        chains.append({
            "chain": chain,
            "duration": log.get("total_duration", 0),
            "success": log.get("success", False),
            "task_name": log.get("task_name", ""),
        })

    # 统计链出现次数
    chain_counter = Counter(c["chain"] for c in chains)

    # 过滤出重复模式
    patterns = []
    for chain, count in chain_counter.items():
        if count < min_count:
            continue
        if len(chain) < min_chain_len:
            continue

        # 计算该模式的统计
        matching = [c for c in chains if c["chain"] == chain]
        avg_dur = sum(c["duration"] for c in matching) / len(matching)
        success_count = sum(1 for c in matching if c["success"])
        success_rate = success_count / len(matching) if matching else 0

        patterns.append({
            "pattern": list(chain),
            "count": count,
            "avg_duration": round(avg_dur, 1),
            "success_rate": round(success_rate, 2),
            "task_names": list(set(c["task_name"] for c in matching)),
        })

    # 按出现次数降序
    patterns.sort(key=lambda x: x["count"], reverse=True)
    return patterns


# ── 6.2 动态软技能文档生成 ──────────────────────────────────────────────────

SOFT_SKILL_GEN_SYSTEM_PROMPT = (
    "你是一个机器人技能文档工程师。\n"
    "根据重复出现的任务模式, 生成一个新的软技能文档 (SKILL.md)。\n"
    "软技能是对硬技能的策略组合, 不是代码, 而是知识文档。\n"
    "LLM 阅读此文档后可以自主组合硬技能完成任务。\n\n"
    "文档格式严格按以下模板, 直接输出 Markdown, 不要代码块包裹。"
)

SOFT_SKILL_TEMPLATE = """# {name} -- {title}

## 概述
{description}

## 使用时机
{when_to_use}

## 推荐策略
{strategy}

## 关键参数
{key_params}

## 注意事项
{notes}

## 历史经验
(待系统运行后自动更新)

## 组合的硬技能
{hard_skills}"""


def generate_soft_skill_doc(
    pattern: dict,
    llm_client,
    existing_skills: list = None,
) -> Optional[dict]:
    """
    根据检测到的模式, 用 LLM 生成软技能文档。

    Args:
        pattern: detect_patterns() 返回的单个模式 dict
        llm_client: LLMClient 实例
        existing_skills: 已有软技能名称列表, 避免重复生成

    Returns:
        dict: {"name": str, "content": str} 或 None
    """
    chain = pattern["pattern"]
    task_names = pattern.get("task_names", [])
    count = pattern.get("count", 0)
    avg_dur = pattern.get("avg_duration", 0)
    success_rate = pattern.get("success_rate", 0)

    existing_skills = existing_skills or []
    chain_str = " -> ".join(chain)
    tasks_str = ", ".join(task_names[:5])

    user_prompt = (
        f"以下技能组合在历史任务中重复出现了 {count} 次:\n\n"
        f"技能链: {chain_str}\n"
        f"相关任务: {tasks_str}\n"
        f"平均耗时: {avg_dur}s\n"
        f"成功率: {success_rate*100:.0f}%\n\n"
        f"已有的软技能: {', '.join(existing_skills) if existing_skills else '(无)'}\n\n"
        f"请为这个模式生成一个新的软技能文档。要求:\n"
        f"1. 为技能取一个合适的 snake_case 名称\n"
        f"2. 按模板格式生成完整文档\n"
        f"3. 如果与已有技能高度相似, 在第一行输出 SKIP 并说明原因\n\n"
        f"先输出一行: NAME: <skill_name>\n"
        f"然后输出完整的 Markdown 文档。"
    )

    try:
        raw = llm_client.chat([
            {"role": "system", "content": SOFT_SKILL_GEN_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ], temperature=0.5, max_tokens=600)
    except Exception as e:
        logger.error(f"[DynamicSkillGen] LLM 调用失败: {e}")
        return None

    if not raw or "SKIP" in raw.split("\n")[0]:
        logger.info(f"[DynamicSkillGen] LLM 建议跳过: {raw[:100] if raw else '空响应'}")
        return None

    # 解析 NAME 行
    name = None
    lines = raw.strip().split("\n")
    for i, line in enumerate(lines):
        if line.strip().startswith("NAME:"):
            name = line.strip()[5:].strip().lower().replace(" ", "_").replace("-", "_")
            # 文档内容从 NAME 行之后开始
            raw = "\n".join(lines[i+1:]).strip()
            break

    if not name:
        # 尝试从第一个 # 标题提取
        match = re.search(r"^#\s+(\w+)", raw, re.MULTILINE)
        if match:
            name = match.group(1).lower()
        else:
            name = "_".join(chain[:2]) + "_combo"

    # 清理名称
    name = re.sub(r"[^a-z0-9_]", "", name)
    if not name:
        name = "auto_skill"

    if name in existing_skills:
        logger.info(f"[DynamicSkillGen] 技能 '{name}' 已存在, 跳过")
        return None

    logger.info(f"[DynamicSkillGen] 生成新软技能: {name}")
    return {"name": name, "content": raw}


# ── 6.3 淘汰机制 ────────────────────────────────────────────────────────────

def get_retirement_candidates(
    soft_skill_manager,
    skill_evolution=None,
    max_age_days: int = 30,
    min_usage: int = 1,
) -> list:
    """
    识别应该淘汰的软技能。

    淘汰条件 (满足任一):
    - 创建超过 max_age_days 天但从未被引用
    - 在技能进化历史中连续评级为 poor
    - 文档内容过短 (< 50字, 可能是生成失败的残留)

    Args:
        soft_skill_manager: SoftSkillManager 实例
        skill_evolution: SkillEvolution 实例 (可选)
        max_age_days: 最大未使用天数
        min_usage: 最少使用次数

    Returns:
        list[dict]: [{"name": str, "reason": str}]
    """
    import os
    import time

    candidates = []
    now = time.time()
    max_age_seconds = max_age_days * 86400

    for name in soft_skill_manager.list_skills():
        info = soft_skill_manager._cache.get(name, {})
        doc_path = info.get("path", "")
        full_text = info.get("full_text", "")

        # 检查文档长度
        if len(full_text) < 50:
            candidates.append({"name": name, "reason": "文档内容过短(< 50字), 可能是生成失败"})
            continue

        # 检查文件年龄
        if doc_path and os.path.exists(doc_path):
            file_age = now - os.path.getmtime(doc_path)
            if file_age > max_age_seconds:
                # 检查是否有使用记录
                if skill_evolution:
                    history = skill_evolution._history.get(name, [])
                    if len(history) < min_usage:
                        candidates.append({
                            "name": name,
                            "reason": f"创建超{max_age_days}天且使用不足{min_usage}次",
                        })

        # 检查是否连续 poor
        if skill_evolution:
            history = skill_evolution._history.get(name, [])
            if len(history) >= 3:
                last_3 = history[-3:]
                if all(r.get("performance") == "poor" for r in last_3):
                    candidates.append({
                        "name": name,
                        "reason": "连续3次评级为poor",
                    })

    return candidates


def retire_skills(soft_skill_manager, candidates: list, dry_run: bool = True) -> list:
    """
    执行软技能淘汰。

    Args:
        soft_skill_manager: SoftSkillManager 实例
        candidates: get_retirement_candidates() 返回的候选列表
        dry_run: True 时只返回将被删除的列表, 不实际删除

    Returns:
        list[str]: 被淘汰的技能名称
    """
    retired = []
    for c in candidates:
        name = c["name"]
        if dry_run:
            logger.info(f"[DynamicSkillGen] 淘汰候选 (dry_run): {name} -- {c['reason']}")
        else:
            if soft_skill_manager.remove_skill(name):
                logger.info(f"[DynamicSkillGen] 已淘汰: {name} -- {c['reason']}")
                retired.append(name)
    return retired
