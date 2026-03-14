"""
reflection_engine.py
反思引擎: 任务执行完成后, 由 LLM 生成结构化反思, 自动更新 MEMORY.md 和 SKILLS.md。

核心流程:
    任务结束 -> 收集执行上下文(TaskLog + WorldState + SkillStats)
            -> 构造反思 prompt -> LLM 生成反思 JSON
            -> 解析并写入 MEMORY.md / SKILLS.md
"""

import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(__file__).parent.parent / "robot_profile"
MEMORY_FILE = PROFILE_DIR / "MEMORY.md"
SKILLS_FILE = PROFILE_DIR / "SKILLS.md"

# ── 反思 system prompt ──

REFLECTION_SYSTEM_PROMPT = (
    "你是一个机器人任务反思分析器。\n"
    "你的职责是分析每次任务执行的完整上下文, 提取有价值的经验和教训。\n"
    "你的分析将被写入机器人的长期记忆, 帮助它在未来做出更好的决策。\n\n"
    "分析原则:\n"
    "1. 关注可迁移的经验, 而非一次性的具体数据\n"
    "2. 对失败任务深入分析根因, 而非只描述现象\n"
    "3. 技能反馈要具体可操作: 推荐参数、使用条件、注意事项\n"
    "4. 环境知识要稳定持久: 不记录偶发事件, 记录规律性发现\n"
    "5. 策略更新要保守: 只有充分证据时才建议改变策略\n\n"
    "输出严格 JSON, 不要包含任何额外文字或代码块标记。"
)

REFLECTION_OUTPUT_SCHEMA = '''{
  "summary": "<任务概要, 1句话>",
  "outcome_analysis": "<结果分析: 成功/失败的核心原因>",
  "environment_insights": ["<环境新知识, 可为空数组>"],
  "task_lessons": ["<任务规划和执行的经验>"],
  "skill_feedback": [
    {
      "skill_name": "<技能名>",
      "performance": "good|acceptable|poor",
      "suggestion": "<具体改进建议, 无则null>",
      "recommended_params": {}
    }
  ],
  "strategy_update": "<策略偏好更新, 无则null>"
}'''


def build_reflection_prompt(
    task_name, task_success, task_duration,
    skill_trace, perception_events,
    replans, emergency_stops, obstacles,
    world_state_snapshot, skill_stats, existing_memory,
):
    """构建反思用户提示词。"""
    trace_lines = []
    for s in skill_trace:
        status = "OK" if s.get("success") else "FAIL"
        err = f" err={s.get('error_msg')}" if s.get("error_msg") else ""
        trace_lines.append(f"  {s.get('skill_name','?')} [{status}] 耗时={s.get('duration',0):.1f}s{err}")
    trace_str = "\n".join(trace_lines) or "  (无)"

    event_lines = [f"  - [{e.get('event_type','?')}] {e.get('summary','')}" for e in perception_events]
    events_str = "\n".join(event_lines) or "  (无)"

    stats_lines = []
    for st in skill_stats:
        rate = st.get("success_rate", -1)
        rate_str = f"{rate*100:.0f}%" if rate >= 0 else "N/A"
        stats_lines.append(f"  {st['skill_name']}: 成功率={rate_str} 平均耗时={st.get('average_cost_time',0):.1f}s 执行{st.get('total_executions',0)}次")
    stats_str = "\n".join(stats_lines) or "  (无历史记录)"

    robots_lines = [
        f"  {rid}: pos={rd.get('position','?')} battery={rd.get('battery','?')}% status={rd.get('status','?')}"
        for rid, rd in world_state_snapshot.get("robots", {}).items()
    ]
    robots_str = "\n".join(robots_lines) or "  (无)"

    mem_snippet = existing_memory[:500] if existing_memory else "(空)"

    return (
        f"请分析以下任务执行记录, 生成结构化反思。\n\n"
        f"## 任务信息\n- 名称: {task_name}\n- 结果: {'成功' if task_success else '失败'}\n"
        f"- 总耗时: {task_duration:.1f}s\n- 重规划: {replans}次\n"
        f"- 应急停止: {emergency_stops}次\n- 遇到障碍: {obstacles}个\n\n"
        f"## 技能执行链\n{trace_str}\n\n"
        f"## 感知事件\n{events_str}\n\n"
        f"## 技能历史统计\n{stats_str}\n\n"
        f"## 执行时世界状态\n{robots_str}\n\n"
        f"## 当前长期记忆(参考, 避免重复记录)\n{mem_snippet}\n\n"
        f"---\n\n请输出以下 JSON:\n{REFLECTION_OUTPUT_SCHEMA}"
    )


def parse_reflection(raw):
    """解析 LLM 输出的反思 JSON, 容忍 markdown 代码块和多余文字。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.warning(f"[ReflectionEngine] JSON 解析失败: {raw[:200]}")
    return None


# ── 文件读写工具 ──

def _read_file(path):
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _append_to_section(content, section_name, entries):
    """向 markdown 的指定 ## section 追加条目。"""
    header = f"## {section_name}"
    if header not in content:
        content = content.rstrip() + f"\n\n{header}\n\n" + "\n".join(entries) + "\n"
        return content

    lines = content.split("\n")
    result = []
    i = 0
    inserted = False

    while i < len(lines):
        line = lines[i]
        result.append(line)

        if line.strip() == header and not inserted:
            i += 1
            while i < len(lines) and lines[i].strip() == "":
                result.append(lines[i])
                i += 1
            if i < len(lines) and "(暂无" in lines[i]:
                for entry in entries:
                    result.append(entry)
                result.append("")
                i += 1
                inserted = True
            else:
                while i < len(lines) and not lines[i].startswith("## "):
                    result.append(lines[i])
                    i += 1
                if result and result[-1].strip() != "":
                    result.append("")
                for entry in entries:
                    result.append(entry)
                result.append("")
                inserted = True
        else:
            i += 1

    return "\n".join(result)


# ── MEMORY.md 更新 ──

def update_memory(reflection):
    """将反思结果追加到 MEMORY.md。"""
    content = _read_file(MEMORY_FILE)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    updates = {}

    for ins in reflection.get("environment_insights", []):
        if ins and isinstance(ins, str) and ins.strip():
            updates.setdefault("环境知识", []).append(f"- [{ts}] {ins.strip()}")

    summary = reflection.get("summary", "")
    outcome = reflection.get("outcome_analysis", "")
    if summary:
        entry = f"- [{ts}] {summary}"
        if outcome:
            entry += f" -- {outcome}"
        updates.setdefault("任务经验", []).append(entry)
    for lesson in reflection.get("task_lessons", []):
        if lesson and isinstance(lesson, str) and lesson.strip():
            updates.setdefault("任务经验", []).append(f"  - {lesson.strip()}")

    strat = reflection.get("strategy_update")
    if strat and isinstance(strat, str) and strat.strip() and strat.lower() != "null":
        updates.setdefault("策略偏好", []).append(f"- [{ts}] {strat.strip()}")

    if not updates:
        logger.info("[ReflectionEngine] 无新增记忆, 跳过 MEMORY.md")
        return

    for section, entries in updates.items():
        content = _append_to_section(content, section, entries)

    MEMORY_FILE.write_text(content, encoding="utf-8")
    total = sum(len(v) for v in updates.values())
    logger.info(f"[ReflectionEngine] MEMORY.md 更新 (+{total} 条)")


# ── SKILLS.md 更新 ──

def update_skills(reflection, skill_stats):
    """根据反思结果和最新统计数据更新 SKILLS.md 中技能的表现数据。"""
    content = _read_file(SKILLS_FILE)
    if not content:
        return

    fb_map = {fb["skill_name"]: fb for fb in reflection.get("skill_feedback", []) if fb.get("skill_name")}
    stats_map = {st["skill_name"]: st for st in skill_stats if st.get("skill_name")}
    if not fb_map and not stats_map:
        return

    lines = content.split("\n")
    new_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("### "):
            skill_name = line[4:].strip()
            new_lines.append(line)
            i += 1

            st = stats_map.get(skill_name)
            fb = fb_map.get(skill_name)

            if st or fb:
                old_notes = ""
                old_params = ""
                while i < len(lines) and not lines[i].startswith("### ") and not lines[i].startswith("## "):
                    stripped = lines[i].strip()
                    if stripped.startswith("- 注意事项:") and not fb:
                        old_notes = stripped[len("- 注意事项:"):].strip()
                    if stripped.startswith("- 推荐参数:") and not fb:
                        old_params = stripped[len("- 推荐参数:"):].strip()
                    i += 1

                if st and st.get("total_executions", 0) > 0:
                    rate = st.get("success_rate", -1)
                    rate_s = f"{rate*100:.0f}%" if rate >= 0 else "待统计"
                    new_lines.append(f"- 成功率: {rate_s} ({st['total_executions']}次执行)")
                    new_lines.append(f"- 平均耗时: {st.get('average_cost_time', 0):.1f}s")
                else:
                    new_lines.append("- 成功率: 待统计")
                    new_lines.append("- 平均耗时: 待统计")

                if fb and fb.get("recommended_params"):
                    new_lines.append(f"- 推荐参数: {json.dumps(fb['recommended_params'], ensure_ascii=False)}")
                elif old_params:
                    new_lines.append(f"- 推荐参数: {old_params}")

                if fb and fb.get("suggestion"):
                    new_lines.append(f"- 注意事项: {fb['suggestion']}")
                elif old_notes:
                    new_lines.append(f"- 注意事项: {old_notes}")

                if fb:
                    new_lines.append(f"- 表现评级: {fb.get('performance', '?')}")

                new_lines.append("")
            else:
                # 技能无更新, 保留原样
                pass
        else:
            new_lines.append(line)
            i += 1

    SKILLS_FILE.write_text("\n".join(new_lines), encoding="utf-8")
    updated = [n for n in set(list(fb_map.keys()) + list(stats_map.keys()))]
    logger.info(f"[ReflectionEngine] SKILLS.md 更新: {updated}")


# ══════════════════════════════════════════════════════════════════════════════
#  ReflectionEngine 主类
# ══════════════════════════════════════════════════════════════════════════════

class ReflectionEngine:
    """
    反思引擎。任务完成后调用 reflect() 进行反思和记忆更新。

    支持两种存储方式（优先向量库，降级到文件）：
    - 有 memory_manager：反思结果存入向量库（episodic/skill/world）
    - 无 memory_manager：写入 MEMORY.md / SKILLS.md 文件

    用法:
        engine = ReflectionEngine(llm_client, skill_memory, memory_manager)
        reflection = engine.reflect(report, world_state)
    """

    def __init__(self, llm_client=None, skill_memory=None, memory_manager=None):
        self._llm_client = llm_client
        self._skill_memory = skill_memory
        self._memory_manager = memory_manager

    def reflect(self, report, world_state, task_logger=None):
        """
        对一次任务执行进行反思。

        Args:
            report: PlanExecutionReport 或包含以下字段的 dict:
                task, success, cost_time/total_duration,
                step_results (list of ExecutionResult)
            world_state: WorldModel.get_world_state() 的快照
            task_logger: TaskLogger 实例(可选, 用于获取感知事件等额外信息)

        Returns:
            dict | None: 解析后的反思 JSON, 或 None(LLM 调用失败时)
        """
        if self._llm_client is None:
            logger.warning("[ReflectionEngine] 无 LLM 客户端, 跳过反思")
            return None

        # 提取 report 字段(兼容 dataclass 和 dict)
        if hasattr(report, 'task'):
            task_name = report.task
            task_success = report.success
            task_duration = getattr(report, 'cost_time', 0.0)
            step_results = getattr(report, 'step_results', [])
        else:
            # dict 格式: AgentLoop 用 "task_name", AgentRuntime 用 "task"
            task_name = report.get("task_name", report.get("task", "unknown"))
            task_success = report.get("success", False)
            task_duration = report.get("cost_time", report.get("total_duration", 0.0))
            step_results = report.get("step_results", [])

        # 构建 skill_trace
        skill_trace = []
        for r in step_results:
            if hasattr(r, 'skill'):
                skill_trace.append({
                    "skill_name": r.skill,
                    "duration": r.cost_time,
                    "success": r.success,
                    "error_msg": r.error_msg if hasattr(r, 'error_msg') else None,
                })
            elif isinstance(r, dict):
                skill_trace.append({
                    "skill_name": r.get("skill", r.get("skill_name", "?")),
                    "duration": r.get("cost_time", r.get("duration", 0)),
                    "success": r.get("success", False),
                    "error_msg": r.get("error_msg"),
                })

        # 获取感知事件(从 TaskLogger)
        perception_events = []
        replans = 0
        emergency_stops = 0
        obstacles = 0
        if task_logger and task_logger.current_task:
            tl = task_logger.current_task
            perception_events = [
                {"event_type": e.event_type, "summary": e.summary}
                for e in tl.perception_events
            ]
            replans = tl.replans
            emergency_stops = tl.emergency_stops
            obstacles = tl.obstacles_encountered

        # 获取技能统计
        skill_stats = []
        if self._skill_memory:
            skill_stats = self._skill_memory.get_all_skill_reliabilities()

        # 读取现有记忆
        existing_memory = _read_file(MEMORY_FILE)

        # 构建 prompt
        user_prompt = build_reflection_prompt(
            task_name=task_name,
            task_success=task_success,
            task_duration=task_duration,
            skill_trace=skill_trace,
            perception_events=perception_events,
            replans=replans,
            emergency_stops=emergency_stops,
            obstacles=obstacles,
            world_state_snapshot=world_state,
            skill_stats=skill_stats,
            existing_memory=existing_memory,
        )

        # 调用 LLM
        logger.info(f"[ReflectionEngine] 开始反思: {task_name}")
        try:
            raw = self._llm_client.chat([
                {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ], temperature=0.3, max_tokens=800)
        except Exception as e:
            logger.error(f"[ReflectionEngine] LLM 调用失败: {e}")
            return None

        # 解析反思
        reflection = parse_reflection(raw)
        if reflection is None:
            return None

        logger.info(f"[ReflectionEngine] 反思完成: {reflection.get('summary', '')}")

        # 更新 MEMORY.md（文件模式，始终执行作为备份）
        try:
            update_memory(reflection)
        except Exception as e:
            logger.error(f"[ReflectionEngine] MEMORY.md 更新失败: {e}")

        # 更新 SKILLS.md
        try:
            update_skills(reflection, skill_stats)
        except Exception as e:
            logger.error(f"[ReflectionEngine] SKILLS.md 更新失败: {e}")

        # 存入向量记忆库（v2.0 新增）
        if self._memory_manager:
            try:
                self._store_to_vector_memory(reflection, task_name, task_success, skill_trace)
            except Exception as e:
                logger.error(f"[ReflectionEngine] 向量记忆存储失败: {e}")

        return reflection

    def _store_to_vector_memory(self, reflection, task_name, task_success, skill_trace):
        """将反思结果存入向量记忆库的各层。"""
        mm = self._memory_manager

        # 1. 任务经历 → episodic 层
        summary = reflection.get("summary", "")
        outcome = reflection.get("outcome_analysis", "")
        lessons = reflection.get("task_lessons", [])
        episode_text = f"任务: {task_name}\n结果: {'成功' if task_success else '失败'}\n"
        if summary:
            episode_text += f"概要: {summary}\n"
        if outcome:
            episode_text += f"分析: {outcome}\n"
        for lesson in lessons:
            if lesson and isinstance(lesson, str):
                episode_text += f"经验: {lesson}\n"
        mm.store_episode({
            "task": task_name,
            "success": task_success,
            "summary": episode_text,
        })

        # 2. 技能反馈 → skill 层
        for fb in reflection.get("skill_feedback", []):
            skill_name = fb.get("skill_name", "")
            if not skill_name:
                continue
            perf = fb.get("performance", "")
            suggestion = fb.get("suggestion", "")
            skill_text = f"技能: {skill_name} 表现: {perf}"
            if suggestion:
                skill_text += f" 建议: {suggestion}"
            mm.update_skill_stats(
                skill_name,
                success=(perf in ("good", "acceptable")),
                cost_time=0,
            )

        # 3. 环境知识 → world 层
        for insight in reflection.get("environment_insights", []):
            if insight and isinstance(insight, str) and insight.strip():
                mm.store_world_knowledge(insight, source=f"reflect:{task_name}")
