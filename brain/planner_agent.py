"""
planner_agent.py
Brain 模块核心：规划智能体。

交互模型：
    ┌─────────────────────────────────────────────────────────┐
    │  system prompt（固定角色 + 技能表 + 当前环境语义信息）      │  ← 每次调用前构建
    ├─────────────────────────────────────────────────────────┤
    │  user prompt（用户/上层系统的自然语言任务指令）              │  ← 透传用户输入
    └─────────────────────────────────────────────────────────┘

LLM 输出格式（JSON）：
    {
      "reasoning": "...",
      "plan": [
        {
          "step": 1,
          "skill": "fly_to",
          "doc_path": "skills/fly_to/skill.md",
          "robot": "UAV_1",
          "parameters": { "target_position": [10, 20, -43] }
        }
      ]
    }

调用入口：plan(task, world_state, skill_registry) -> dict
LLM 厂商/模型通过 config.py + llm_client.py 统一管理。
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_client import get_client, LLMClient

# ── 身份文件路径 ─────────────────────────────────────────────────────────────

PROFILE_DIR = Path(__file__).parent.parent / "robot_profile"

def _read_profile(filename: str, max_lines: int = 0) -> str:
    """读取 robot_profile 下的文件内容，不存在则返回空字符串。"""
    p = PROFILE_DIR / filename
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8").strip()
    if max_lines > 0:
        lines = text.splitlines()
        text = "\n".join(lines[:max_lines])
    return text


# ── System Prompt 构建 ───────────────────────────────────────────────────────

def _build_skill_table(skill_catalog: list[dict]) -> str:
    """Level 1: 紧凑技能摘要表, 控制在 ~200 tokens。"""
    from skills.skill_loader import build_skill_summary
    return build_skill_summary(skill_catalog)


def _build_env_summary(world_state: dict) -> str:
    """将当前世界状态转换为 system prompt 内嵌的语义摘要。"""
    robots  = world_state.get("robots", {})
    targets = world_state.get("targets", [])

    robot_lines = [
        f"  - {rid}: 类型={d.get('robot_type','?')} "
        f"电量={d.get('battery','?')}% "
        f"状态={d.get('status','?')} "
        f"位置={d.get('position','?')}"
        for rid, d in robots.items()
    ]
    robots_str  = "\n".join(robot_lines) or "  （无可用机器人）"
    targets_str = json.dumps(targets, ensure_ascii=False) if targets else "  （暂无已知目标）"

    return f"### 可用机器人\n{robots_str}\n\n### 已知目标\n{targets_str}"


def _build_perception_summary() -> str:
    """从感知守护线程获取环境感知摘要。"""
    try:
        from perception.daemon import get_daemon
        daemon = get_daemon()
        if daemon and daemon.is_running:
            return daemon.get_summary()
    except ImportError:
        pass
    return ""


def build_system_prompt(world_state: dict, skill_catalog: list[dict],
                        task: str = "", memory_manager=None) -> str:
    """构建完整 system prompt：身份 + 身体认知 + 经验记忆 + 感知摘要 + 技能表 + 环境 + 输出格式。

    Args:
        world_state: 世界状态字典
        skill_catalog: 技能目录列表
        task: 当前任务描述（用于向量检索相关记忆）
        memory_manager: MemoryManager 实例（有则用向量检索，无则读 MEMORY.md 文件）
    """
    skill_table = _build_skill_table(skill_catalog)
    env_summary = _build_env_summary(world_state)

    # 读取身份文件
    soul = _read_profile("SOUL.md")
    body = _read_profile("BODY.md")
    skills_md = _read_profile("SKILLS.md", max_lines=60)
    world_map = _read_profile("WORLD_MAP.md", max_lines=60)  # 场景地理信息

    # 经验记忆：优先向量检索，降级到全文读取
    memory = ""
    if memory_manager and task:
        try:
            memory = memory_manager.get_context_for_planning(task)
        except Exception:
            memory = _read_profile("MEMORY.md", max_lines=50)
    else:
        memory = _read_profile("MEMORY.md", max_lines=50)

    # 构建身份段落
    identity_section = ""
    if soul:
        identity_section += f"""
## 你的身份

{soul}
"""
    if body:
        identity_section += f"""
## 你的身体

{body}
"""

    # 构建经验段落
    experience_section = ""
    if memory and "暂无" not in memory:
        experience_section += f"""
## 历史经验

以下是你从过去任务中积累的经验, 规划时请参考:

{memory}
"""
    if skills_md and "待统计" not in skills_md[:200]:
        experience_section += f"""
## 技能表现记录

{skills_md}
"""

    # 构建感知段落
    perception_section = ""
    perception_str = _build_perception_summary()
    if perception_str:
        perception_section = f"""
## 实时环境感知

{perception_str}
"""

    return f"""你就是一架智能无人机 (UAV_1)。你有自己的身体、传感器和技能。
当操作员给你任务时, 你需要思考如何用自己的技能完成它, 然后输出结构化执行计划。
你不是一个外部调度员 -- 你就是执行任务的那架无人机。用"我"来思考。
{identity_section}
## 你的职责

分析操作员的任务指令, 思考如何用自己的技能完成, 输出结构化执行计划。
{experience_section}{perception_section}
## 场景地图

{world_map if world_map else "(无场景地图)"}

---

## 我的技能表

{skill_table}

---

## 当前状态

{env_summary}

---

## 规划规则

1. 只能选择技能表中列出的技能 (skill 字段必须与 name 完全一致)
2. robot 字段填写你自己的 ID (通常是 UAV_1)
3. 步骤按执行依赖顺序排列
4. doc_path 字段直接从技能表的"文档路径"复制, 若为空则填 ""
5. parameters 字段根据技能的输入参数说明填写具体值
6. 只使用你确定自己拥有的技能, 不要编造不存在的技能

---

## 输出格式

严格输出以下 JSON, 不要包含任何额外文字或代码块标记:

{{
  "reasoning": "<用第一人称简要说明规划思路, 1-3句>",
  "plan": [
    {{
      "step": 1,
      "skill": "<skill_name>",
      "doc_path": "<skill.md 路径, 直接从技能表复制>",
      "robot": "<你自己的 robot_id>",
      "parameters": {{}}
    }}
  ]
}}

若无法完成任务 (技能不匹配/条件不满足), plan 输出空数组并在 reasoning 中说明原因。"""


# ── 响应解析 ─────────────────────────────────────────────────────────────────

def _parse_plan_response(raw: str, task: str) -> dict:
    """解析 LLM 输出的 JSON，容忍 LLM 附带多余文字的情况。"""
    try:
        result = json.loads(raw)
        result.setdefault("task", task)
        return result
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        try:
            result = json.loads(match.group())
            result.setdefault("task", task)
            return result
        except json.JSONDecodeError:
            pass

    return {
        "task":      task,
        "reasoning": f"LLM 输出解析失败，原始内容片段: {raw[:300]}",
        "plan":      [],
    }


# ── 主接口 ───────────────────────────────────────────────────────────────────

def plan(
    task: str,
    world_state: dict,
    skill_registry,
    client: LLMClient | None = None,
    two_stage: bool = True,
    on_token: callable = None,
    memory_manager=None,
) -> dict:
    """
    核心规划接口：接收任务指令，返回结构化执行计划。

    两级技能加载流程：
        Stage 1: L1 摘要表 (~200 tokens) → LLM 输出初步 plan
        Stage 2: 加载涉及技能的 SKILL.md 详情 → LLM 确认/修正参数
        (two_stage=False 时跳过 Stage 2，只做单轮规划)

    Args:
        on_token: 流式回调，每收到一个 token 就调用 on_token(text)

    Args:
        task:           自然语言任务指令（原样作为 user prompt）
        world_state:    WorldModel.get_world_state() 返回的世界状态
        skill_registry: SkillRegistry 实例（提供精简技能表）
        client:         LLMClient 实例；为 None 时自动从 config 取 planner 配置
        two_stage:      是否启用两阶段规划，默认 True
        memory_manager: MemoryManager 实例（用于向量检索相关记忆，可选）

    Returns:
        dict: {
            "task":      str,
            "reasoning": str,
            "plan": [
                {
                    "step":       int,
                    "skill":      str,
                    "doc_path":   str,
                    "robot":      str,
                    "parameters": dict
                }
            ]
        }
    """
    from skills.skill_loader import load_skill_docs_for_plan

    if client is None:
        client = get_client(module="planner")

    skill_catalog = skill_registry.get_skill_catalog()

    print(f"[PlannerAgent] 任务: {task}")
    print(f"[PlannerAgent] 模型: {client.model}  服务: {client.provider_url}")
    print(f"[PlannerAgent] 技能: {[s['name'] for s in skill_catalog]}")
    print(f"[PlannerAgent] 机器人: {list(world_state.get('robots', {}).keys())}")
    print(f"[PlannerAgent] 两阶段规划: {'开启' if two_stage else '关闭'}")
    if memory_manager:
        print(f"[PlannerAgent] 记忆系统: 向量检索模式")

    system_prompt = build_system_prompt(world_state, skill_catalog,
                                         task=task, memory_manager=memory_manager)

    try:
        # ── Stage 1: L1 摘要表 → 初步 plan ──────────────────────────────
        raw = client.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": task},
        ], on_chunk=on_token)
        result = _parse_plan_response(raw, task)
        steps = result.get("plan", [])
        print(f"[PlannerAgent] Stage 1 完成，步骤数: {len(steps)}")
        print(f"[PlannerAgent] 推理: {result.get('reasoning', '')}")
        for s in steps:
            print(f"  step {s.get('step')}: {s.get('skill')} → robot={s.get('robot')}")

        # ── Stage 2: L2 技能详情文档 → 确认/修正 plan ────────────────────
        if two_stage and steps:
            skill_docs = load_skill_docs_for_plan(steps)
            if skill_docs:
                print(f"[PlannerAgent] Stage 2: 加载了 {skill_docs.count('###')} 个技能详情文档")
                refine_prompt = f"""{skill_docs}

---

你的初步计划:
{json.dumps(result, ensure_ascii=False, indent=2)}

---

请根据上面的技能详情文档审查你的初步计划。
检查: 参数值是否在合理范围内, 前提条件是否满足, 执行顺序是否正确, 注意事项是否已考虑。
如果需要修正, 输出修正后的完整 JSON 计划; 如果无需修正, 原样输出。
输出格式同之前, 严格 JSON, 不要额外文字。"""

                raw2 = client.chat([
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": task},
                    {"role": "assistant", "content": raw},
                    {"role": "user",   "content": refine_prompt},
                ])
                result2 = _parse_plan_response(raw2, task)
                steps2 = result2.get("plan", [])
                if steps2:
                    result = result2
                    steps = steps2
                    print(f"[PlannerAgent] Stage 2 完成，修正后步骤数: {len(steps)}")
                else:
                    print(f"[PlannerAgent] Stage 2 未产生有效计划，保留 Stage 1 结果")
            else:
                print(f"[PlannerAgent] 无可用技能文档，跳过 Stage 2")

        for s in steps:
            print(f"  [最终] step {s.get('step')}: {s.get('skill')} → robot={s.get('robot')} params={s.get('parameters', {})}")
        return result

    except RuntimeError as e:
        print(f"[PlannerAgent] 错误: {e}")
        return {"task": task, "reasoning": str(e), "plan": []}


# ── 带工具调用的规划接口 ──────────────────────────────────────────────────────

def plan_with_tools(
    task: str,
    world_state: dict,
    skill_registry,
    tool_registry,
    client: LLMClient | None = None,
    max_tool_iterations: int = 6,
) -> dict:
    """
    带工具调用的规划接口：LLM 可在生成计划前主动查询工具补充实时信息。

    工作流程：
        system prompt（技能表 + 环境语义 + 工具说明）
            ↓
        tool_call_loop（LLM 自主调用工具 → 工具执行 → 继续规划）
            ↓
        最终 LLM 回复（JSON 格式执行计划）

    Args:
        task               : 自然语言任务指令
        world_state        : WorldModel.get_world_state() 返回的世界状态
        skill_registry     : SkillRegistry 实例
        tool_registry      : ToolRegistry 实例（包含所有可用工具）
        client             : LLMClient 实例；None 时自动从 config 取 tool_caller 配置
        max_tool_iterations: 最大工具调用轮数，默认 6

    Returns:
        dict: 与 plan() 返回格式相同：
            {
                "task":      str,
                "reasoning": str,
                "plan": [...]
            }

    Note:
        需要 LLM 支持 Function Calling（tool_calls 响应）。
        qwen3.5:9b 为推理模型，非流式模式可能超时，建议改用 qwen2.5:7b 或云端模型。
    """
    # 延迟导入避免循环依赖
    from tools.tool_call_loop import tool_call_loop

    if client is None:
        client = get_client(module="tool_caller")

    skill_catalog = skill_registry.get_skill_catalog()

    print(f"[PlannerAgent+Tools] 任务: {task}")
    print(f"[PlannerAgent+Tools] 模型: {client.model}  服务: {client.provider_url}")
    print(f"[PlannerAgent+Tools] 技能: {[s['name'] for s in skill_catalog]}")
    print(f"[PlannerAgent+Tools] 工具: {[t.name for t in tool_registry]}")

    # 在标准 system prompt 末尾追加工具使用说明
    base_prompt = build_system_prompt(world_state, skill_catalog)
    tool_names  = ", ".join(t.name for t in tool_registry)
    tool_hint   = f"""
---

## 工具调用说明

在生成执行计划前，你可以调用以下工具查询实时信息以辅助决策：
    {tool_names}

调用工具的时机（示例）：
- 不确定某台机器人是否空闲 → 调用 get_robot_status 或 get_all_robots
- 需要确认目标位置 → 调用 get_targets
- 需要找最近的机器人 → 调用 find_nearest_robot
- 需要参考历史经验 → 调用 retrieve_episode 或 get_skill_reliability
- 需要计算两点距离 → 调用 calculate_distance

工具调用完毕后，输出最终 JSON 执行计划（格式同之前）。"""

    system_prompt = base_prompt + tool_hint

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": task},
    ]

    try:
        raw = tool_call_loop(
            client=client,
            messages=messages,
            tool_registry=tool_registry,
            max_iterations=max_tool_iterations,
            temperature=0.3,
        )
        result = _parse_plan_response(raw, task)
        steps = result.get("plan", [])
        print(f"[PlannerAgent+Tools] 规划完成，步骤数: {len(steps)}")
        print(f"[PlannerAgent+Tools] 推理: {result.get('reasoning', '')}")
        for s in steps:
            print(f"  step {s.get('step')}: {s.get('skill')} → robot={s.get('robot')} doc='{s.get('doc_path','')}'")
        return result

    except RuntimeError as e:
        print(f"[PlannerAgent+Tools] 错误: {e}")
        return {"task": task, "reasoning": str(e), "plan": []}
