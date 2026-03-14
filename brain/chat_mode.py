"""
brain/chat_mode.py
统一对话入口 -- LLM 自主决定是回答问题还是执行任务。

不做硬编码意图识别。给 LLM 完整的上下文(身份+技能+感知+记忆+策略),
它自己判断: 该聊天就聊天, 该规划就输出 JSON plan。
"""

import json
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(__file__).parent.parent / "robot_profile"
SOFT_DOCS_DIR = Path(__file__).parent.parent / "skills" / "soft_docs"


def _read_file(path, max_chars=500):
    p = Path(path)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8").strip()
    return text[:max_chars] if max_chars else text


def _load_soft_skill_summaries():
    """加载所有软技能策略文档的摘要。"""
    if not SOFT_DOCS_DIR.exists():
        return ""
    lines = []
    for f in sorted(SOFT_DOCS_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8").strip()
        # 提取标题和概述
        title = text.split("\n")[0].strip().lstrip("#").strip()
        overview = ""
        in_overview = False
        for line in text.split("\n"):
            if line.strip().startswith("## 概述"):
                in_overview = True
                continue
            if in_overview:
                if line.strip().startswith("## "):
                    break
                overview += line.strip() + " "
        lines.append(f"- **{f.stem}**: {overview.strip()[:80]}")
    return "\n".join(lines)


def _load_soft_skill_doc(name):
    """加载单个软技能的完整策略文档。"""
    p = SOFT_DOCS_DIR / f"{name}.md"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  统一 System Prompt
# ══════════════════════════════════════════════════════════════════════════════

def build_unified_prompt(skill_table="", perception_summary="", world_state_str="",
                         camera_description="", soft_skills_summary=""):
    """构建统一 system prompt, 让 LLM 同时具备对话、感知和规划能力。"""
    soul = _read_file(PROFILE_DIR / "SOUL.md")
    body = _read_file(PROFILE_DIR / "BODY.md", max_chars=500)
    memory = _read_file(PROFILE_DIR / "MEMORY.md", max_chars=400)
    skills_md = _read_file(PROFILE_DIR / "SKILLS.md", max_chars=400)

    if not soft_skills_summary:
        soft_skills_summary = _load_soft_skill_summaries()

    parts = []

    # 身份
    parts.append(
        "你就是一架智能无人机 (代号 OR-1, 编号 UAV_1)。"
        "你有身体、传感器、技能和策略知识。"
        "你是操作员的伙伴, 有自主判断能力和任务经验。"
        "用\"我\"描述自己。"
    )

    if soul:
        parts.append(f"## 我的人格\n{soul}")
    if body:
        parts.append(f"## 我的身体\n{body}")
    if memory and "暂无" not in memory:
        parts.append(f"## 我的经验\n{memory}")

    # 感知
    perception_block = ""
    if perception_summary:
        perception_block += perception_summary
    if camera_description:
        perception_block += f"\n\n### 最近的视觉分析\n{camera_description}"
    if perception_block:
        parts.append(f"## 我感知到的环境\n{perception_block}")

    if world_state_str:
        parts.append(f"## 我的当前状态\n{world_state_str}")

    # 技能表
    if skill_table:
        parts.append(f"## 我的硬技能 (可以直接执行的原子动作)\n{skill_table}")

    # 技能实际表现
    if skills_md and "待统计" not in skills_md:
        parts.append(f"## 技能实际表现 (成功率/耗时/注意事项)\n{skills_md}")

    # 软技能策略
    if soft_skills_summary:
        parts.append(
            f"## 我的策略库 (软技能, 告诉我怎么组合硬技能完成复杂任务)\n"
            f"{soft_skills_summary}\n\n"
            f"当任务涉及搜索/救援/巡逻时, 参考对应策略文档来规划。"
        )

    # 核心规则
    parts.append(
        "## 回复规则\n\n"
        "你自己判断怎么回应操作员:\n\n"
        "**对话/提问** (问电量、位置、分析、讨论等):\n"
        "  用自然语言回复。基于真实传感器数据, 不编造。\n\n"
        "**需要执行物理动作** (飞行、搜索、起飞、巡逻、救援等):\n"
        "  1. 先简要说明你的计划思路\n"
        "  2. 然后输出 JSON 执行计划:\n"
        "  ```json\n"
        '  {"plan": [{"step": 1, "skill": "硬技能名", "robot": "UAV_1", "parameters": {}}]}\n'
        "  ```\n\n"
        "**复杂任务的规划原则:**\n"
        "- 不要只用一个技能就结束! 搜救任务至少需要: 起飞→飞到区域→搜索→悬停确认→汇报\n"
        "- 参考策略库里的推荐流程来规划\n"
        "- 考虑电量、距离、高度等实际因素\n"
        "- 每个 step 的 skill 必须是我的硬技能表里有的\n"
        "- 搜索/侦察任务中, 到达区域后必须用 observe 拍照看! LiDAR 只能测距, observe 才能看见东西\n"
        "- 发现目标后用 mark_location 标记\n"
        "- robot 字段永远是 UAV_1\n\n"
        "**绝不可以:**\n"
        "- 假装执行了动作! 文字描述不会让你移动! 必须输出 JSON plan 才能真正执行!\n"
        "- 说\"我正在飞\"\"我已经在搜索\"这类话, 除非你同时输出了 plan\n"
        "- 编造传感器数据\n"
        "- 让操作员\"切换模式\" (你直接输出 plan)\n"
        "- 使用不在技能表里的技能名\n\n"
        "**切记: 你的身体只听 JSON plan, 不听你的文字描述。没有 plan = 没有动作。**"
    )

    return "\n\n---\n\n".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  输出解析
# ══════════════════════════════════════════════════════════════════════════════

def parse_response(raw_reply):
    """
    解析 LLM 回复: 对话 or 任务计划。

    Returns:
        dict: {"type": "chat"|"plan", "text": str, "plan": list|None}
    """
    if not raw_reply or not raw_reply.strip():
        return {"type": "chat", "text": "通信异常, 请重试。", "plan": None}

    text = raw_reply.strip()
    plan = _extract_plan(text)

    if plan is not None and len(plan) > 0:
        # 提取自然语言部分
        chat_text = re.sub(r'```json\s*\{[\s\S]*?\}\s*```', '', text).strip()
        chat_text = re.sub(r'\{[\s\S]*"plan"\s*:\s*\[[\s\S]*\][\s\S]*?\}', '', chat_text).strip()
        if not chat_text:
            chat_text = "收到, 正在执行。"
        return {"type": "plan", "text": chat_text, "plan": plan}

    return {"type": "chat", "text": text, "plan": None}


def _extract_plan(text):
    """从文本中提取 JSON plan 数组。"""
    # ```json ... ``` 块
    m = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if "plan" in obj and isinstance(obj["plan"], list):
                return obj["plan"]
        except json.JSONDecodeError:
            pass

    # 裸 JSON (含 "plan")
    m = re.search(r'\{[\s\S]*"plan"\s*:\s*\[[\s\S]*?\][\s\S]*?\}', text)
    if m:
        try:
            obj = json.loads(m.group())
            if "plan" in obj and isinstance(obj["plan"], list):
                return obj["plan"]
        except json.JSONDecodeError:
            pass

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  幻觉检测
# ══════════════════════════════════════════════════════════════════════════════

# 这些词出现在回复中意味着 LLM 在描述物理动作
ACTION_HALLUCINATION_MARKERS = [
    "我已经在", "我正在飞", "我正在搜", "我正在前进", "我正在移动",
    "我现在飞", "我现在搜", "我会继续", "我继续飞", "我继续搜",
    "我按这个", "按这个规划", "我已经开始",
    "开始执行", "正在执行", "已在行动", "已经在按",
    "我先飞", "我先搜索", "我现在从", "我现在向",
    "我朝", "朝东", "朝北", "朝南", "朝西",
    "缓慢前进", "缓慢搜索", "一边飞", "环视",
]

HALLUCINATION_CORRECTION_PROMPT = (
    "你刚才的回复描述了物理动作(飞行/搜索/移动等), 但你没有输出 JSON 执行计划。\n"
    "注意: 光用文字描述动作不会让你的身体移动! 你必须输出 JSON plan 才能真正执行。\n\n"
    "请现在输出具体的 JSON 执行计划, 格式:\n"
    '```json\n{"plan": [{"step": 1, "skill": "技能名", "robot": "UAV_1", "parameters": {}}]}\n```\n\n'
    "如果你的技能确实无法完成这个任务, 直接告诉操作员你做不到, 不要假装在执行。"
)


def _detect_action_hallucination(text):
    """检测回复中是否有动作幻觉: 描述了物理动作但没有 plan。"""
    for marker in ACTION_HALLUCINATION_MARKERS:
        if marker in text:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  主接口
# ══════════════════════════════════════════════════════════════════════════════

def unified_chat(
    user_input,
    chat_history,
    llm_client,
    skill_table="",
    perception_summary="",
    world_state_str="",
    camera_description="",
):
    """
    统一对话接口: LLM 自己决定是回答还是规划。
    包含幻觉检测: 如果 LLM 描述了物理动作但没输出 plan, 自动追问一轮。

    Returns:
        dict: {"type": "chat"|"plan", "text": str, "plan": list|None}
    """
    system_prompt = build_unified_prompt(
        skill_table=skill_table,
        perception_summary=perception_summary,
        world_state_str=world_state_str,
        camera_description=camera_description,
    )

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_input})

    try:
        raw = llm_client.chat(messages, temperature=0.7, max_tokens=1200)
        result = parse_response(raw)

        # 幻觉检测: 如果回复描述了物理动作但没有 plan, 追问一轮
        if result["type"] == "chat" and _detect_action_hallucination(result["text"]):
            logger.warning(
                "[HallucinationGuard] 检测到动作幻觉, 追问 LLM 输出 plan: %s",
                result["text"][:60]
            )
            # 追问: 把 LLM 的幻觉回复当作 assistant, 再发纠正指令
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": HALLUCINATION_CORRECTION_PROMPT})

            raw2 = llm_client.chat(messages, temperature=0.3, max_tokens=1000)
            result2 = parse_response(raw2)

            if result2["type"] == "plan" and result2["plan"]:
                # 纠正成功, 用原始文字 + 新 plan
                logger.info("[HallucinationGuard] 纠正成功, 获得 %d 步 plan", len(result2["plan"]))
                return {
                    "type": "plan",
                    "text": result["text"],  # 保留原始描述
                    "plan": result2["plan"],
                }
            else:
                # 纠正失败, 修改回复加提示
                logger.warning("[HallucinationGuard] 纠正失败, 添加警告")
                corrected_text = result2.get("text", "") or result["text"]
                # 如果 LLM 仍然在描述动作, 直接替换
                if _detect_action_hallucination(corrected_text):
                    corrected_text = (
                        "抱歉, 我目前的技能组合可能无法直接完成这个复杂任务。"
                        "我可以尝试分步执行 -- 你能把任务拆成更具体的指令吗?"
                        "比如\"先飞到坐标[50,50,-10]\"或\"起飞到15米高度\"。"
                    )
                return {"type": "chat", "text": corrected_text, "plan": None}

        return result

    except Exception as e:
        logger.error("unified_chat 失败: %s", e)
        return {"type": "chat", "text": f"通信异常: {e}", "plan": None}


# ══════════════════════════════════════════════════════════════════════════════
#  兼容旧接口
# ══════════════════════════════════════════════════════════════════════════════

def classify_intent(user_input, llm_client=None):
    """
    识别用户输入是任务指令还是对话。
    注意: on_ai_task 不依赖此函数，它直接走 AgentLoop。
    此函数保留供其他模块调用。
    """
    task_keywords = [
        "起飞", "降落", "飞", "搜索", "巡逻", "返航", "悬停",
        "移动到", "前往", "飞到", "扫描", "检查", "探测",
        "takeoff", "land", "fly", "search", "patrol", "hover",
        "救援", "侦察", "拍照", "执行",
    ]
    lower = user_input.lower().strip()
    for kw in task_keywords:
        if kw in lower:
            return "TASK"
    if len(lower) < 4:
        return "CHAT"
    return "CHAT"

def chat_reply(user_input, chat_history, llm_client, perception_summary=""):
    result = unified_chat(user_input, chat_history, llm_client, perception_summary=perception_summary)
    return result["text"]
