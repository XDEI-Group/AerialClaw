"""
exector.py
执行器：负责将单个技能分派给指定机器人执行，是 Runtime 层最底层的执行单元。

职责：
    - 调用 Robot Interface（此处为技能实例的 execute()）
    - 检查机器人前置条件
    - 返回标准化执行结果

Functions:
    execute_skill(robot_id, skill_name, parameters, world_model, skill_registry)
        -> ExecutionResult
"""

import time
from dataclasses import dataclass, field


@dataclass
class ExecutionResult:
    """
    单次技能执行结果，对应 README 中的 ExecutionResult 协议。
    """
    success: bool
    reward: float = 0.0          # 执行奖励（成功=1.0，失败=0.0，部分=0-1之间）
    output: dict = field(default_factory=dict)
    logs: list = field(default_factory=list)
    error_msg: str = ""
    skill: str = ""
    robot: str = ""
    cost_time: float = 0.0


class Executor:
    """
    技能执行器。
    接收单条执行指令（robot + skill + parameters），完成底层执行并返回结果。

    依赖：
        - robot_registries: dict[robot_id, SkillRegistry]  — 每个机器人独立的技能注册表
        - WorldModel：获取机器人当前状态、执行后更新状态

    技能注册表按机器人隔离，UAV_1 的 takeoff 执行历史不会污染 UAV_2 的 takeoff。
    """

    def __init__(self, robot_registries: dict, world_model):
        """
        Args:
            robot_registries: {robot_id: SkillRegistry}，每台机器人独立注册表
            world_model:      WorldModel 实例
        """
        self._robot_registries = robot_registries   # {robot_id → SkillRegistry}
        self._world_model = world_model

    def execute_skill(
        self,
        robot_id: str,
        skill_name: str,
        parameters: dict,
    ) -> ExecutionResult:
        """
        调用指定技能在指定机器人上执行。

        执行流程：
            1. 从 WorldModel 获取机器人当前状态
            2. 从 SkillRegistry 获取技能实例
            3. 检查前置条件
            4. 执行技能
            5. 将 robot 状态更新为 executing → idle / error
            6. 返回 ExecutionResult

        Args:
            robot_id:   机器人 ID，例如 "UAV_1"
            skill_name: 技能名称，例如 "search_target"
            parameters: 技能执行参数字典

        Returns:
            ExecutionResult: 包含成功标志、奖励、输出、日志
        """
        logs = []
        start = time.time()

        # ── 1. 获取机器人状态 ────────────────────────────────────────────────
        robot_state = self._world_model.get_robot_state(robot_id)
        if not robot_state:
            return ExecutionResult(
                success=False,
                reward=0.0,
                skill=skill_name,
                robot=robot_id,
                error_msg=f"Robot '{robot_id}' not found in WorldModel",
                logs=[f"[Executor] Error: robot '{robot_id}' not registered"],
            )

        # ── 2. 获取该机器人的技能注册表，再取技能实例 ────────────────────────
        registry = self._robot_registries.get(robot_id)
        if registry is None:
            return ExecutionResult(
                success=False,
                reward=0.0,
                skill=skill_name,
                robot=robot_id,
                error_msg=f"Robot '{robot_id}' has no skill registry",
                logs=[f"[Executor] Error: no registry for robot '{robot_id}'"],
            )

        skill = registry.get_skill(skill_name)
        if skill is None:
            # 检查是否是软技能（文档驱动的任务策略）
            try:
                from skills.soft_skill_manager import get_soft_skill_manager
                mgr = get_soft_skill_manager()
                if mgr.skill_exists(skill_name):
                    doc = mgr.get_skill_doc(skill_name)
                    logs.append(f"[Executor] 软技能 '{skill_name}' → 加载策略文档")
                    return ExecutionResult(
                        success=True,
                        reward=0.5,
                        skill=skill_name,
                        robot=robot_id,
                        output={"strategy_doc": doc[:800],
                                "instruction": f"已加载 {skill_name} 策略文档。请仔细阅读并用硬技能逐步执行。"},
                        logs=logs,
                    )
            except Exception:
                pass
            return ExecutionResult(
                success=False,
                reward=0.0,
                skill=skill_name,
                robot=robot_id,
                error_msg=f"Skill '{skill_name}' not registered for robot '{robot_id}'",
                logs=[f"[Executor] Error: skill '{skill_name}' not in {robot_id}'s registry"],
            )

        logs.append(f"[Executor] Dispatching skill='{skill_name}' to robot='{robot_id}'")

        # ── 3. 检查前置条件 ──────────────────────────────────────────────────
        if not skill.check_precondition(robot_state):
            # 对 land/return_to_launch 降级为 warning，仍尝试执行
            if skill_name in ("land", "return_to_launch"):
                logs.append(f"[Executor] 前提检查 WARNING (继续执行): {skill.preconditions}")
            else:
                # 逐条检查，找出具体哪条不满足
                failed = []
                for cond in skill.preconditions:
                    if "battery" in cond:
                        threshold = int("".join(filter(str.isdigit, cond)))
                        actual = robot_state.get("battery", 100)
                        if actual <= threshold:
                            failed.append(f"battery={actual}% (要求>{threshold}%)")
                    elif "robot_type" in cond:
                        expected = cond.split("==")[-1].strip()
                        actual = robot_state.get("robot_type", "unknown")
                        if actual != expected:
                            failed.append(f"robot_type={actual!r} (要求{expected})")
                    elif "in_air" in cond:
                        expected = "True" in cond
                        actual = robot_state.get("in_air", False)
                        if bool(actual) != expected:
                            state_str = "在空中" if actual else "在地面"
                            need_str = "在空中" if expected else "在地面"
                            failed.append(f"in_air={state_str} (要求{need_str})")
                if not failed:
                    failed = skill.preconditions  # fallback
                fail_msg = "；".join(failed)
                return ExecutionResult(
                    success=False,
                    reward=0.0,
                    skill=skill_name,
                    robot=robot_id,
                    error_msg=f"前提条件不满足: {fail_msg}",
                    logs=logs + [f"[Executor] 前提检查失败: {fail_msg}"],
                )

        # ── 4. 更新机器人状态为 executing ───────────────────────────────────
        self._world_model.update_world_state({
            "robots": {robot_id: {"status": "executing"}}
        })

        # ── 5. 执行技能 ──────────────────────────────────────────────────────
        # 将 robot_state 注入到参数中，供 SoftSkill 使用
        exec_input = {**parameters, "robot_state": robot_state}

        try:
            skill_result = skill.execute(exec_input)
        except Exception as e:
            self._world_model.update_world_state({
                "robots": {robot_id: {"status": "error"}}
            })
            cost_time = round(time.time() - start, 4)
            return ExecutionResult(
                success=False,
                reward=0.0,
                skill=skill_name,
                robot=robot_id,
                error_msg=f"Skill execution raised exception: {e}",
                logs=logs + [f"[Executor] Exception: {e}"],
                cost_time=cost_time,
            )

        # ── 6. 更新机器人状态为 idle ─────────────────────────────────────────
        new_status = "idle" if skill_result.success else "error"
        self._world_model.update_world_state({
            "robots": {robot_id: {"status": new_status}}
        })

        cost_time = round(time.time() - start, 4)
        logs.extend(skill_result.logs)
        logs.append(
            f"[Executor] Done: skill='{skill_name}' robot='{robot_id}' "
            f"success={skill_result.success} cost_time={cost_time}s"
        )

        return ExecutionResult(
            success=skill_result.success,
            reward=1.0 if skill_result.success else 0.0,
            output=skill_result.output,
            skill=skill_name,
            robot=robot_id,
            error_msg=skill_result.error_msg,
            logs=logs,
            cost_time=cost_time,
        )
