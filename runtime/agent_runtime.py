"""
agent_runtime.py
运行时调度核心：将 Brain 输出的执行计划转化为实际的机器人技能执行序列。

职责：
    - 接收来自 Brain 的结构化执行计划
    - 按步骤顺序调度 Executor 执行技能
    - 收集执行反馈，写入 Memory 模块（EpisodicMemory、SkillMemory）
    - 监控整体执行状态

核心流程：
    Task → plan(Brain) → execute_plan(Runtime) → dispatch_skill(Executor) → feedback(Memory)

Functions:
    execute_plan(plan)          - 执行完整规划
    dispatch_skill(step)        - 分派单步技能执行
    monitor_execution()         - 获取当前执行状态报告
"""

import time
import uuid
from dataclasses import dataclass, field

from runtime.exector import Executor, ExecutionResult


@dataclass
class PlanExecutionReport:
    """
    整个计划的执行报告。
    """
    task_id: str
    task: str
    total_steps: int
    completed_steps: int
    success: bool
    overall_reward: float
    step_results: list[ExecutionResult] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    logs: list[str] = field(default_factory=list)

    @property
    def cost_time(self) -> float:
        return round(self.end_time - self.start_time, 4)


class AgentRuntime:
    """
    Agent 运行时调度器。
    连接 Brain → Skill → Memory 三层，是系统执行核心。

    依赖注入：
        robot_registries - dict[robot_id, SkillRegistry]，每台机器人独立注册表
        world_model      - WorldModel 实例
        episodic_memory  - EpisodicMemory 实例
        skill_memory     - SkillMemory 实例

    技能注册表按机器人隔离：UAV_1 和 UAV_2 各自持有独立的 takeoff 实例，
    last_execution_status 互不干扰。
    """

    def __init__(
        self,
        robot_registries: dict,
        world_model,
        episodic_memory=None,
        skill_memory=None,
        reflection_engine=None,
        skill_evolution=None,
    ):
        """
        Args:
            robot_registries:  {robot_id: SkillRegistry}，每台机器人独立注册表
            world_model:       WorldModel 实例
            episodic_memory:   EpisodicMemory 实例（可选）
            skill_memory:      SkillMemory 实例（可选）
            reflection_engine: ReflectionEngine 实例（可选，执行后自动反思）
            skill_evolution:   SkillEvolution 实例（可选，跟踪技能进化）
        """
        self._robot_registries = robot_registries   # {robot_id → SkillRegistry}
        self._executor = Executor(robot_registries, world_model)
        self._world_model = world_model
        self._episodic_memory = episodic_memory
        self._skill_memory = skill_memory
        self._reflection_engine = reflection_engine
        self._skill_evolution = skill_evolution

        # 当前执行状态
        self._current_task_id: str | None = None
        self._current_report: PlanExecutionReport | None = None

    # ── 主接口 ───────────────────────────────────────────────────────────────

    def execute_plan(self, plan: dict) -> PlanExecutionReport:
        """
        执行来自 Brain 的完整结构化计划。

        Args:
            plan: Brain.plan() 返回的字典，格式：
                {
                    "task": str,
                    "reasoning": str,
                    "plan": [
                        {"step": int, "skill": str, "robot": str, "parameters": dict}
                    ]
                }

        Returns:
            PlanExecutionReport: 包含每步执行结果、整体成功标志、日志
        """
        task = plan.get("task", "unknown task")
        steps = plan.get("plan", [])
        task_id = str(uuid.uuid4())

        report = PlanExecutionReport(
            task_id=task_id,
            task=task,
            total_steps=len(steps),
            completed_steps=0,
            success=False,
            overall_reward=0.0,
            start_time=time.time(),
        )
        self._current_task_id = task_id
        self._current_report = report

        report.logs.append(f"[Runtime] 开始执行计划: task_id={task_id} steps={len(steps)}")
        report.logs.append(f"[Runtime] 任务: {task}")
        report.logs.append(f"[Runtime] 推理: {plan.get('reasoning', '')}")

        if not steps:
            report.logs.append("[Runtime] 计划为空，跳过执行")
            report.end_time = time.time()
            self._record_episode(report)
            return report

        # 按步骤顺序执行
        all_success = True
        total_reward = 0.0

        for step_data in steps:
            step_num = step_data.get("step", "?")
            report.logs.append(f"[Runtime] 执行步骤 {step_num}: {step_data}")

            result = self.dispatch_skill(step_data)
            report.step_results.append(result)
            total_reward += result.reward

            # 更新技能记忆 + 回写 last_execution_status 到该机器人的 SkillRegistry
            self._record_skill_feedback(result)
            robot_reg = self._robot_registries.get(result.robot)
            if robot_reg:
                robot_reg.update_execution_status(result.skill, result.success)

            if result.success:
                report.completed_steps += 1
                report.logs.append(
                    f"[Runtime] 步骤 {step_num} 成功: "
                    f"skill={result.skill} robot={result.robot}"
                )
            else:
                all_success = False
                report.logs.append(
                    f"[Runtime] 步骤 {step_num} 失败: {result.error_msg}"
                )
                # 遇到失败步骤停止执行（串行依赖模式）
                report.logs.append("[Runtime] 执行中止：步骤失败")
                break

        report.success = all_success
        report.overall_reward = round(
            total_reward / len(steps) if steps else 0.0, 4
        )
        report.end_time = time.time()

        report.logs.append(
            f"[Runtime] 计划执行完成: success={report.success} "
            f"reward={report.overall_reward} cost_time={report.cost_time}s"
        )

        # 记录情节记忆
        self._record_episode(report)

        # 触发反思引擎（异步，不阻塞返回）
        self._trigger_reflection(report)

        self._current_task_id = None
        self._current_report = None

        return report

    def dispatch_skill(self, step: dict) -> ExecutionResult:
        """
        分派单步技能执行指令给 Executor。

        Args:
            step: 单步计划字典，格式：
                {
                    "step": int,
                    "skill": str,
                    "robot": str,
                    "parameters": dict
                }

        Returns:
            ExecutionResult
        """
        robot_id = step.get("robot", "")
        skill_name = step.get("skill", "")
        parameters = step.get("parameters", {})

        return self._executor.execute_skill(robot_id, skill_name, parameters)

    def monitor_execution(self) -> dict:
        """
        获取当前执行状态报告快照。
        若当前无任务执行，返回空闲状态。

        Returns:
            dict: {
                "status": "idle" | "executing",
                "task_id": str | None,
                "task": str,
                "completed_steps": int,
                "total_steps": int,
                "world_state_summary": dict
            }
        """
        world_state = self._world_model.get_world_state()
        robots_summary = {
            rid: {
                "status": rdata.get("status"),
                "battery": rdata.get("battery"),
            }
            for rid, rdata in world_state.get("robots", {}).items()
        }

        if self._current_report is None:
            return {
                "status": "idle",
                "task_id": None,
                "task": "",
                "completed_steps": 0,
                "total_steps": 0,
                "robots": robots_summary,
            }

        report = self._current_report
        return {
            "status": "executing",
            "task_id": report.task_id,
            "task": report.task,
            "completed_steps": report.completed_steps,
            "total_steps": report.total_steps,
            "robots": robots_summary,
        }

    # ── 内部辅助：写入 Memory ────────────────────────────────────────────────

    def _record_episode(self, report: PlanExecutionReport) -> None:
        """将任务执行结果写入 EpisodicMemory。"""
        if self._episodic_memory is None:
            return

        world_state = self._world_model.get_world_state()
        episode = {
            "task_id": report.task_id,
            "task": report.task,
            "environment": str(world_state.get("map", {})),
            "skills_used": [r.skill for r in report.step_results],
            "success": report.success,
            "reward": report.overall_reward,
            "cost_time": report.cost_time,
        }
        self._episodic_memory.store_episode(episode)

    def _record_skill_feedback(self, result: ExecutionResult) -> None:
        """将单次技能执行结果写入 SkillMemory。"""
        if self._skill_memory is None:
            return

        feedback = {
            "task_id": self._current_task_id or "",
            "skill": result.skill,
            "robot": result.robot,
            "success": result.success,
            "cost_time": result.cost_time,
        }
        self._skill_memory.update_skill_statistics(feedback)

    def _trigger_reflection(self, report: PlanExecutionReport) -> None:
        """
        任务执行完成后触发反思引擎。
        在后台线程中执行，不阻塞主流程。
        """
        if self._reflection_engine is None:
            return

        import threading

        def _do_reflect():
            try:
                world_state = self._world_model.get_world_state()
                reflection = self._reflection_engine.reflect(
                    report=report,
                    world_state=world_state,
                )

                if reflection:
                    print(
                        f"[Runtime] 反思完成: {reflection.get('summary', '')}"
                    )
            except Exception as e:
                print(f"[Runtime] 反思失败: {e}")

        t = threading.Thread(target=_do_reflect, daemon=True)
        t.start()
