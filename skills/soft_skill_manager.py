"""
soft_skill_manager.py
软技能管理器 — 基于文档的软技能管理。

设计:
  软技能不再是 Python 类, 而是 SKILL.md 文档。
  LLM 读文档后自己用硬技能组合执行计划。
  
功能:
  - 加载 soft_docs/ 下所有软技能文档
  - 生成软技能摘要表 (供 system prompt L1)
  - 按需加载单个软技能详情
  - 管理软技能的生命周期 (创建/更新/淘汰)
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SOFT_DOCS_DIR = Path(__file__).parent / "soft_docs"


class SoftSkillManager:
    """
    软技能管理器。
    管理 soft_docs/ 下的 SKILL.md 文档。
    """

    def __init__(self, docs_dir: Path = SOFT_DOCS_DIR):
        self._docs_dir = docs_dir
        self._docs_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, dict] = {}  # name -> {path, summary, full_text}
        self._scan()

    def _scan(self):
        """扫描 soft_docs/ 目录, 加载所有软技能文档元信息。"""
        self._cache.clear()
        for f in sorted(self._docs_dir.glob("*.md")):
            name = f.stem
            text = f.read_text(encoding="utf-8").strip()
            # 提取第一行作为标题 (去掉 #)
            first_line = text.split("\n")[0].strip().lstrip("#").strip()
            # 提取 ## 概述 段落作为摘要
            summary = self._extract_section(text, "概述")
            if not summary:
                summary = first_line

            self._cache[name] = {
                "path": str(f),
                "title": first_line,
                "summary": summary,
                "full_text": text,
            }
        logger.info("软技能管理器: 加载 %d 个文档", len(self._cache))

    def _extract_section(self, text: str, section_name: str) -> str:
        """提取 markdown 文档中指定 ## 段落的内容。"""
        lines = text.split("\n")
        capture = False
        result = []
        for line in lines:
            if line.strip().startswith("## ") and section_name in line:
                capture = True
                continue
            if capture and line.strip().startswith("## "):
                break
            if capture:
                result.append(line)
        return "\n".join(result).strip()

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def list_skills(self) -> List[str]:
        """返回所有软技能名称。"""
        return list(self._cache.keys())

    def get_summary_table(self) -> str:
        """
        生成软技能摘要表 (L1), 供 system prompt。
        每个技能一行: 名称 -- 简短描述。
        """
        if not self._cache:
            return ""
        lines = []
        for name, info in self._cache.items():
            lines.append(f"  {name} -- {info['summary'][:40]}")
        return "软技能 (任务策略, 文档驱动):\n" + "\n".join(lines)

    def get_catalog_entries(self) -> List[dict]:
        """
        返回兼容 SkillRegistry 格式的 catalog 条目。
        使软技能文档能与硬技能一起出现在技能摘要表中。
        """
        entries = []
        for name, info in self._cache.items():
            entries.append({
                "name": name,
                "description": info["summary"][:50],
                "skill_type": "soft",
                "robot_type": ["UAV"],  # 默认 UAV, 后续可从文档解析
                "input_schema": {},
                "output_schema": {},
                "last_execution_status": "never",
                "doc_path": info["path"],
            })
        return entries

    def get_skill_doc(self, name: str) -> str:
        """获取指定软技能的完整文档 (L2)。"""
        info = self._cache.get(name)
        return info["full_text"] if info else ""

    def skill_exists(self, name: str) -> bool:
        """检查软技能是否存在。"""
        return name in self._cache

    # ── 管理 ──────────────────────────────────────────────────────────────────

    def create_skill(self, name: str, content: str) -> str:
        """
        创建新的软技能文档。

        Args:
            name:    技能名称 (snake_case)
            content: Markdown 文档内容

        Returns:
            str: 文档路径
        """
        path = self._docs_dir / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        self._scan()  # 重新扫描
        logger.info("创建软技能: %s -> %s", name, path)
        return str(path)

    def update_skill(self, name: str, content: str) -> bool:
        """更新软技能文档内容。"""
        path = self._docs_dir / f"{name}.md"
        if not path.exists():
            return False
        path.write_text(content, encoding="utf-8")
        self._scan()
        logger.info("更新软技能: %s", name)
        return True

    def update_experience(self, name: str, experience: str) -> bool:
        """
        追加经验到软技能文档的 '历史经验' 段落。
        由 ReflectionEngine 调用。
        """
        info = self._cache.get(name)
        if not info:
            return False

        text = info["full_text"]
        # 找到 '## 历史经验' 段落并追加
        marker = "## 历史经验"
        if marker in text:
            idx = text.index(marker) + len(marker)
            # 找下一个 ## 或文末
            next_section = text.find("\n## ", idx)
            if next_section == -1:
                # 追加到文末
                text = text.rstrip() + f"\n- {experience}\n"
            else:
                # 在下一个 ## 前插入
                text = text[:next_section].rstrip() + f"\n- {experience}\n\n" + text[next_section:]
        else:
            # 没有历史经验段落, 追加到文末
            text = text.rstrip() + f"\n\n## 历史经验\n- {experience}\n"

        path = self._docs_dir / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        self._scan()
        return True

    def remove_skill(self, name: str) -> bool:
        """删除软技能文档 (淘汰)。"""
        path = self._docs_dir / f"{name}.md"
        if path.exists():
            path.unlink()
            self._scan()
            logger.info("删除软技能: %s", name)
            return True
        return False

    def refresh(self):
        """重新扫描文档目录。"""
        self._scan()


# ── 全局单例 ──────────────────────────────────────────────────────────────────

_manager: Optional[SoftSkillManager] = None


def get_soft_skill_manager() -> SoftSkillManager:
    """获取全局软技能管理器实例 (懒初始化)。"""
    global _manager
    if _manager is None:
        _manager = SoftSkillManager()
    return _manager
