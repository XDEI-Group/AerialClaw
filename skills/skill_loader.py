"""
skill_loader.py
两级技能加载系统。

Level 1: 技能摘要表 (~200 tokens), 始终在 system prompt 中
Level 2: SKILL.md 详情文档, 按需加载 (LLM 选定技能后注入)

流程:
  1. build_skill_summary() -> 紧凑摘要表 (每次 plan 都带)
  2. planner 第一轮 LLM 调用 -> 输出初步 plan
  3. load_skill_docs_for_plan(plan) -> 加载涉及技能的详情文档
  4. planner 第二轮 LLM 调用 -> 用详情文档确认/修正 plan
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DOCS_DIR = Path(__file__).parent / "docs"
SOFT_DOCS_DIR = Path(__file__).parent / "soft_docs"


def build_skill_summary(skill_catalog: list[dict]) -> str:
    """
    Level 1: 生成紧凑的技能摘要表。
    每个技能一行, 只包含名称、参数和简短描述。
    目标: ~200 tokens。
    """
    if not skill_catalog:
        return "(当前无可用技能)"

    hard = []
    soft = []
    perception = []

    for s in skill_catalog:
        stype = s.get("skill_type", "hard")
        params = ", ".join(s.get("input_schema", {}).keys()) or "无参数"
        desc = s.get("description", "")
        # 截断描述到 30 字
        if len(desc) > 30:
            desc = desc[:30] + "..."
        line = f"  {s['name']}({params}) -- {desc}"

        if stype == "hard":
            hard.append(line)
        elif stype == "soft":
            soft.append(line)
        elif stype == "perception":
            perception.append(line)
        else:
            hard.append(line)

    sections = []
    if hard:
        sections.append("硬技能 (直接控制):\n" + "\n".join(hard))
    if soft:
        sections.append("软技能 (任务策略):\n" + "\n".join(soft))
    if perception:
        sections.append("感知技能:\n" + "\n".join(perception))

    return "\n\n".join(sections)


def load_skill_doc(skill_name: str) -> str:
    """
    Level 2: 按需加载技能详情文档。
    先查 docs/ (硬技能), 再查 soft_docs/ (软技能)。
    返回文档内容, 不存在则返回空字符串。
    """
    # 硬技能文档
    doc_path = DOCS_DIR / f"{skill_name}.md"
    if doc_path.exists():
        return doc_path.read_text(encoding="utf-8").strip()

    # 软技能文档
    soft_path = SOFT_DOCS_DIR / f"{skill_name}.md"
    if soft_path.exists():
        return soft_path.read_text(encoding="utf-8").strip()

    return ""


def load_skill_docs_for_plan(plan_steps: list[dict]) -> str:
    """
    为执行计划中涉及的技能加载详情文档。
    用于第二轮 LLM 调用: 注入详细参数说明、注意事项、执行流程。

    Args:
        plan_steps: LLM 第一轮输出的 plan 步骤列表

    Returns:
        str: 格式化的技能详情文档块, 可直接拼接到 system prompt
    """
    seen = set()
    docs = []
    for step in plan_steps:
        skill_name = step.get("skill", "")
        if skill_name and skill_name not in seen:
            seen.add(skill_name)
            doc = load_skill_doc(skill_name)
            if doc:
                docs.append(f"### {skill_name}\n{doc}")

    if not docs:
        return ""
    return "## 技能详情文档 (按需加载)\n\n以下是你计划中用到的技能的详细文档, 请根据这些信息确认或修正你的参数:\n\n" + "\n\n---\n\n".join(docs)


def list_all_skill_docs() -> dict:
    """列出所有可用的技能文档。返回 {name: path}。"""
    result = {}
    if DOCS_DIR.exists():
        for f in DOCS_DIR.glob("*.md"):
            result[f.stem] = str(f)
    if SOFT_DOCS_DIR.exists():
        for f in SOFT_DOCS_DIR.glob("*.md"):
            result[f.stem] = str(f)
    return result
