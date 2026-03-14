"""
registry.py
技能注册表：管理所有已注册技能，维护技能运行时状态，提供精简技能表供 LLM 消费。

核心职责：
    1. 注册技能实例，注入 doc_path / last_execution_status 运行时字段
    2. 注册时在后台线程触发 LLM 生成 skill.md（非阻塞）
    3. 提供 get_skill_catalog() —— 精简技能表，专供 system prompt 使用
    4. 提供 update_execution_status() —— 执行后由 Runtime 回写执行状态

精简技能表（skill catalog）格式（每条）：
    {
        "name":                  str,   # 技能名称
        "description":           str,   # 一句话功能描述
        "skill_type":            str,   # "hard" | "soft" | "perception"
        "robot_type":            list,  # 适用机器人类型
        "input_schema":          dict,  # 输入参数说明
        "output_schema":         dict,  # 输出字段说明
        "last_execution_status": str,   # "never" | "success" | "failed"
        "doc_path":              str,   # skill.md 路径
    }
"""

from typing import Optional
from skills.base_skill import Skill


class SkillRegistry:
    """
    技能注册表。
    注册时自动生成 skill.md；维护 last_execution_status 和 doc_path 运行时状态。
    """

    def __init__(self, auto_generate_doc: bool = True):
        """
        Args:
            auto_generate_doc: 是否在注册时自动生成 skill.md，默认 True
                               LLM 厂商/模型由 config.py 统一配置，无需在此指定
        """
        self._registry: dict[str, Skill] = {}
        self.auto_generate_doc = auto_generate_doc

    # ── 注册 ─────────────────────────────────────────────────────────────────

    def register_skill(self, skill: Skill) -> None:
        """
        注册技能实例。
        注册后：
            - 后台线程触发 LLM 生成 skill.md，doc_path 写入技能对象
            - last_execution_status 初始化为 "never"

        Args:
            skill: 继承自 Skill 的技能实例

        Raises:
            ValueError: 技能名称为空或重复注册
        """
        if not skill.name:
            raise ValueError("Skill must have a non-empty name.")
        if skill.name in self._registry:
            raise ValueError(f"Skill '{skill.name}' is already registered.")

        # 初始化运行时状态
        skill.last_execution_status = "never"
        skill.doc_path = ""

        self._registry[skill.name] = skill

        if self.auto_generate_doc:
            self._trigger_doc_generation(skill)

    def _trigger_doc_generation(self, skill: Skill) -> None:
        """后台线程调用 LLM 生成 skill.md，完成后将路径写回 skill.doc_path。
        LLM 客户端由 llm_client.get_client(module='doc_generator') 自动从 config 读取。
        """
        import threading
        from skills.skill_doc_generator import generate_skill_doc

        def _generate():
            doc_path = generate_skill_doc(skill)   # client 由 config 自动决定
            if doc_path:
                skill.doc_path = str(doc_path)

        thread = threading.Thread(
            target=_generate,
            name=f"SkillDocGen-{skill.name}",
            daemon=True,
        )
        thread.start()

    # ── 查询 ─────────────────────────────────────────────────────────────────

    def get_skill(self, name: str) -> Optional[Skill]:
        """按名称获取技能实例。"""
        return self._registry.get(name)

    def get_skill_catalog(self) -> list[dict]:
        """
        返回精简技能表，专供 system prompt 使用。
        包含硬技能 + 感知技能 + 软技能文档。

        Returns:
            list[dict]: 精简技能表条目列表
        """
        entries = [skill.get_catalog_entry() for skill in self._registry.values()]
        # 合并软技能文档条目
        try:
            from skills.soft_skill_manager import get_soft_skill_manager
            mgr = get_soft_skill_manager()
            entries.extend(mgr.get_catalog_entries())
        except Exception:
            pass
        return entries

    def list_skills(self) -> list[dict]:
        """
        返回完整技能元信息列表，供 skill_doc_generator 等内部模块使用。

        Returns:
            list[dict]: 完整元信息列表（含 preconditions/cost 等）
        """
        return [skill.get_metadata() for skill in self._registry.values()]

    def get_skills_by_robot_type(self, robot_type: str) -> list[Skill]:
        """按机器人类型过滤技能。"""
        return [
            skill for skill in self._registry.values()
            if robot_type in skill.robot_type
        ]

    # ── 状态回写 ──────────────────────────────────────────────────────────────

    def update_execution_status(self, skill_name: str, success: bool) -> None:
        """
        执行完成后由 Runtime 回写技能的 last_execution_status。
        此状态会在下次生成 system prompt 时反映到技能表中。

        Args:
            skill_name: 技能名称
            success:    本次执行是否成功
        """
        skill = self._registry.get(skill_name)
        if skill:
            skill.last_execution_status = "success" if success else "failed"

    # ── 魔术方法 ─────────────────────────────────────────────────────────────

    def __contains__(self, name: str) -> bool:
        return name in self._registry

    def __len__(self) -> int:
        return len(self._registry)

    def __repr__(self):
        return f"<SkillRegistry skills={list(self._registry.keys())}>"


# 全局单例注册表
skill_registry = SkillRegistry()
