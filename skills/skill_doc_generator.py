"""
skill_doc_generator.py
技能文档生成器：在运行时调用 LLM，为每个技能自动生成 skill.md 文档。

工作流程：
    1. 从技能对象提取完整元信息（get_metadata()）
    2. 构建 system + user prompt，引导 LLM 生成标准 Markdown 文档
    3. 通过 llm_client.get_client() 调用 LLM（厂商/模型由 config.py 统一配置）
    4. 将 md 文档写入 skills/<skill_name>/skill.md
    5. 将路径写回 skill.doc_path

调用时机：
    由 SkillRegistry.register_skill() 在注册时在后台线程自动触发。
    也可手动调用 generate_skill_doc(skill) 或 generate_all_skill_docs(registry)。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_client import get_client, LLMClient
from config import SKILLS_ROOT


# ── Prompt ───────────────────────────────────────────────────────────────────

_DOC_SYSTEM_PROMPT = """你是机器人技能文档工程师。根据技能元信息生成简洁的 Markdown 技能文档。
直接输出 Markdown，不要代码块包裹，不要额外说明，控制在 400 字以内。"""


def _build_doc_user_prompt(skill_meta: dict) -> str:
    """根据技能元信息构建文档生成的 user prompt。"""
    name          = skill_meta.get("name", "unknown")
    description   = skill_meta.get("description", "")
    skill_type    = skill_meta.get("skill_type", "soft")
    robot_type    = ", ".join(skill_meta.get("robot_type", [])) or "任意"
    preconditions = skill_meta.get("preconditions", [])
    input_schema  = skill_meta.get("input_schema",  {})
    output_schema = skill_meta.get("output_schema", {})
    cost          = skill_meta.get("cost", 0.0)

    preconditions_str = "、".join(preconditions) or "无"
    input_str  = "、".join(f"`{k}`:{v}" for k, v in input_schema.items())  or "无"
    output_str = "、".join(f"`{k}`:{v}" for k, v in output_schema.items()) or "无"

    skill_type_cn = {
        "hard":       "硬技能",
        "soft":       "软技能",
        "perception": "感知技能",
    }.get(skill_type, skill_type)

    return f"""为技能 `{name}` 生成 skill.md，要求包含以下章节，内容简洁：

# Skill: {name}

## 概述
（1-2句说明用途）

## 基本信息
| 字段 | 值 |
|---|---|
| 名称 | `{name}` |
| 类型 | {skill_type_cn} |
| 适用机器人 | {robot_type} |
| 执行成本 | {cost} |

## 前置条件
{preconditions_str}

## 输入参数
{input_str}

## 输出字段
{output_str}

## 执行流程
（简要描述）

## 调用示例
（5行以内的 Python 示例）

## 注意事项
（1-2条）

描述：{description}
"""


# ── 文档写入 ─────────────────────────────────────────────────────────────────

def _save_skill_doc(skill_name: str, content: str) -> Path:
    """将 Markdown 内容写入 skills/<skill_name>/skill.md，目录不存在时自动创建。"""
    skill_dir = SKILLS_ROOT / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    doc_path = skill_dir / "skill.md"
    doc_path.write_text(content, encoding="utf-8")
    return doc_path


# ── 主入口 ───────────────────────────────────────────────────────────────────

def generate_skill_doc(
    skill,
    client: LLMClient | None = None,
) -> Path | None:
    """
    为指定技能对象生成 skill.md 文档。
    失败时仅打印警告，不抛出异常，不阻断技能注册流程。

    Args:
        skill:  继承自 Skill 的技能实例
        client: LLMClient 实例；为 None 时自动从 config 取 doc_generator 配置

    Returns:
        Path | None: 文档保存路径；失败时返回 None
    """
    if client is None:
        client = get_client(module="doc_generator")

    skill_meta = skill.get_metadata()
    skill_name = skill_meta.get("name", "unknown")

    print(f"[SkillDocGenerator] 生成文档: '{skill_name}' (model={client.model})")

    try:
        user_prompt = _build_doc_user_prompt(skill_meta)
        md_content  = client.chat([
            {"role": "system", "content": _DOC_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ])

        if not md_content:
            print(f"[SkillDocGenerator] 警告: 模型返回空内容，跳过 '{skill_name}'")
            return None

        doc_path = _save_skill_doc(skill_name, md_content)
        print(f"[SkillDocGenerator] 完成: {doc_path}")
        return doc_path

    except RuntimeError as e:
        print(f"[SkillDocGenerator] 警告: {e}，技能注册不受影响")
        return None
    except Exception as e:
        print(f"[SkillDocGenerator] 未知错误: {e}")
        return None


def generate_all_skill_docs(
    registry,
    client: LLMClient | None = None,
) -> list[Path]:
    """
    批量为注册表中所有技能生成文档，完成后自动将路径写回 skill.doc_path。

    Args:
        registry: SkillRegistry 实例
        client:   LLMClient 实例；为 None 时自动从 config 取配置

    Returns:
        list[Path]: 成功生成的文档路径列表
    """
    if client is None:
        client = get_client(module="doc_generator")

    results     = []
    skill_names = [meta["name"] for meta in registry.list_skills()]
    total       = len(skill_names)
    print(f"[SkillDocGenerator] 批量生成 {total} 个文档 (model={client.model})")

    for i, name in enumerate(skill_names, 1):
        skill = registry.get_skill(name)
        if skill:
            print(f"[SkillDocGenerator] [{i}/{total}] {name}")
            path = generate_skill_doc(skill, client=client)
            if path:
                skill.doc_path = str(path)
                results.append(path)

    print(f"[SkillDocGenerator] 完成: {len(results)}/{total} 成功")
    return results
