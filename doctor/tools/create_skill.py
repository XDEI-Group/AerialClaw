"""
doctor/tools/create_skill.py — 生成新硬技能（向上推送）
"""
from __future__ import annotations
import ast
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_SKILLS_DIR = _BASE_DIR / "skills"
_DOCS_DIR = _SKILLS_DIR / "docs"

TOOL_DEF = {
    "name": "create_skill",
    "description": "创建新的硬技能类和对应文档。用于设备有新能力时向上推送技能。",
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "技能名称，如 grab / release / scan",
            },
            "skill_code": {
                "type": "string",
                "description": "技能类的 Python 代码（继承 Skill）",
            },
            "skill_doc": {
                "type": "string",
                "description": "技能文档 (markdown)，描述用法和参数",
            },
            "target_file": {
                "type": "string",
                "description": "写入的技能文件名，默认 motor_skills.py。新设备类型可指定新文件。",
            },
        },
        "required": ["skill_name", "skill_code", "skill_doc"],
    },
}


def execute(
    skill_name: str = "",
    skill_code: str = "",
    skill_doc: str = "",
    target_file: str = "motor_skills.py",
    **kwargs,
) -> dict:
    """创建新硬技能。"""
    if not skill_name or not skill_code:
        return {"success": False, "error": "skill_name 和 skill_code 不能为空"}

    # 语法检查
    try:
        ast.parse(skill_code)
    except SyntaxError as e:
        return {"success": False, "error": f"技能代码语法错误: {e}"}

    # 检查是否继承 Skill
    if "Skill" not in skill_code:
        return {"success": False, "error": "技能代码必须继承 Skill 基类"}

    # 追加到技能文件
    target = _SKILLS_DIR / target_file
    if not target.exists():
        return {"success": False, "error": f"目标文件不存在: {target_file}"}

    try:
        existing = target.read_text(encoding="utf-8")

        # 检查是否已存在同名技能
        if f'name = "{skill_name}"' in existing:
            return {"success": False, "error": f"技能 {skill_name} 已存在于 {target_file}"}

        # 追加代码
        new_content = existing.rstrip() + "\n\n\n" + skill_code.strip() + "\n"
        target.write_text(new_content, encoding="utf-8")
        logger.info(f"新技能 {skill_name} 已写入 {target_file}")
    except Exception as e:
        return {"success": False, "error": f"写入失败: {e}"}

    # 写技能文档
    if skill_doc:
        try:
            _DOCS_DIR.mkdir(parents=True, exist_ok=True)
            doc_path = _DOCS_DIR / f"{skill_name}.md"
            doc_path.write_text(skill_doc.strip() + "\n", encoding="utf-8")
            logger.info(f"技能文档 {skill_name}.md 已创建")
        except Exception as e:
            logger.warning(f"文档写入失败: {e}")

    return {
        "success": True,
        "skill_name": skill_name,
        "target_file": target_file,
        "doc_created": bool(skill_doc),
        "summary": f"新技能 {skill_name} 已创建并写入 {target_file}",
    }
