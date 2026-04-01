"""
swarm/coordinator.py — 子节点（Coordinator）

区域协调节点，管辖若干执行设备。
职责：
    1. 向主节点注册
    2. 接收主节点的自然语言任务
    3. 用 LLM 将区域任务分解为单设备任务，下发给执行节点
    4. 收集执行节点报告，生成区域报告上报主节点
"""

import time
import uuid
import logging
from typing import Optional

from swarm.protocol import (
    NodeRole, NodeInfo, MessageType, TaskState, SwarmMessage,
    make_task_assign, make_task_status, make_task_report,
)
from swarm.node import SwarmNode

logger = logging.getLogger(__name__)


class Coordinator:
    """
    子节点区域协调器。
    
    使用方式：
        coord = Coordinator(
            port=6100, 
            commander_url="http://commander-host:6000",
            llm_client=llm,
        )
        coord.start()
        # 之后自动接收主节点任务并协调下属执行设备
    """

    def __init__(self, port: int = 6100, commander_url: str = "http://localhost:6000",
                 llm_client=None, node_id: str = None, name: str = "Coordinator"):
        self.node_info = NodeInfo(
            node_id=node_id or f"coord-{str(uuid.uuid4())[:4]}",
            role=NodeRole.COORDINATOR,
            name=name,
            host="0.0.0.0",
            port=port,
            capabilities=["area_coordination", "report_aggregation"],
        )
        self.commander_url = commander_url
        self.swarm = SwarmNode(self.node_info, parent_url=commander_url)
        self.llm = llm_client

        # 当前执行的任务 {task_id → info}
        self._active_tasks: dict[str, dict] = {}
        # 执行节点报告收集 {task_id → {drone_id → report}}
        self._drone_reports: dict[str, dict] = {}

        # 注册消息处理
        self.swarm.on(MessageType.TASK_ASSIGN, self._on_task_assign)
        self.swarm.on(MessageType.TASK_STATUS, self._on_drone_status)
        self.swarm.on(MessageType.TASK_REPORT, self._on_drone_report)

    def start(self):
        """启动子节点"""
        self.swarm.start()
        logger.info(f"Coordinator '{self.node_info.name}' started on port {self.node_info.port}")

    def stop(self):
        self.swarm.stop()

    # ── 接收主节点任务 ────────────────────────────────────────────────────────

    def _on_task_assign(self, msg: SwarmMessage) -> dict:
        """收到主节点分配的任务"""
        task_id = msg.payload.get("task_id", "")
        instruction = msg.payload.get("instruction", "")
        logger.info(f"[{self.node_info.node_id}] Received task {task_id}: {instruction[:80]}...")

        # 上报任务开始
        status_msg = make_task_status(self.node_info.node_id, task_id, TaskState.IN_PROGRESS,
                                       "开始分解任务并分配给执行节点")
        self.swarm.send(self.commander_url, status_msg)

        # 在新线程中执行（不阻塞消息接收）
        import threading
        t = threading.Thread(target=self._execute_task, args=(task_id, instruction), daemon=True)
        t.start()
        return {"status": "accepted", "task_id": task_id}

    def _execute_task(self, task_id: str, instruction: str):
        """执行区域任务的完整流程"""
        try:
            # 1. 获取可用执行节点
            drones = self.swarm.get_alive_children()
            if not drones:
                self._report_failure(task_id, "没有可用的执行节点")
                return

            # 2. LLM 分解为单机任务
            sub_tasks = self._decompose_for_drones(instruction, drones)

            # 3. 下发给各执行节点
            self._drone_reports[task_id] = {}
            for drone_id, drone_instruction in sub_tasks.items():
                sub_task_id = f"{task_id}-{drone_id}"
                msg = make_task_assign(
                    sender_id=self.node_info.node_id,
                    receiver_id=drone_id,
                    task_id=sub_task_id,
                    instruction=drone_instruction,
                )
                self.swarm.send_to_child(drone_id, msg)
                self._active_tasks[sub_task_id] = {
                    "parent_task": task_id,
                    "drone": drone_id,
                    "state": TaskState.PENDING,
                }
                logger.info(f"[{self.node_info.node_id}] → {drone_id}: {drone_instruction[:60]}...")

            # 4. 等待执行节点报告
            deadline = time.time() + 240  # 4 分钟超时
            while time.time() < deadline:
                collected = self._drone_reports.get(task_id, {})
                if len(collected) >= len(sub_tasks):
                    break
                time.sleep(2)

            # 5. 生成区域报告
            collected = self._drone_reports.get(task_id, {})
            area_report = self._generate_area_report(instruction, collected)

            # 6. 上报主节点
            report_msg = make_task_report(
                sender_id=self.node_info.node_id,
                task_id=task_id,
                report=area_report,
            )
            self.swarm.send(self.commander_url, report_msg)

            # 上报完成状态
            status_msg = make_task_status(self.node_info.node_id, task_id, TaskState.COMPLETED,
                                           "区域报告已提交")
            self.swarm.send(self.commander_url, status_msg)

        except Exception as e:
            logger.error(f"[{self.node_info.node_id}] Task {task_id} failed: {e}")
            self._report_failure(task_id, str(e))

    def _report_failure(self, task_id: str, reason: str):
        """上报任务失败"""
        status_msg = make_task_status(self.node_info.node_id, task_id, TaskState.FAILED, reason)
        self.swarm.send(self.commander_url, status_msg)

    # ── 任务分解（LLM）─────────────────────────────────────────────────────

    def _decompose_for_drones(self, instruction: str, drone_ids: list) -> dict:
        """将区域任务分解为单机任务"""
        if not self.llm:
            return {did: instruction for did in drone_ids}

        # 收集各执行节点能力
        drones_info = []
        for did in drone_ids:
            drone = self.swarm.children.get(did)
            if drone:
                drones_info.append(f"- {did} (名称: {drone.name}, 能力: {drone.capabilities})")

        prompt = f"""你是区域协调员。你需要将一个区域任务分解为具体的单设备任务。

区域任务：{instruction}

可用的执行设备：
{chr(10).join(drones_info)}

为每个设备生成具体的任务指令，包括：
1. 具体要执行的操作或前往的目标
2. 需要完成的观察/搜索/操作行为
3. 完成标准

请严格按如下 JSON 格式输出：
{{
    "{drone_ids[0]}": "具体任务指令...",
    ...
}}"""

        try:
            response = self.llm.chat(prompt)
            import json
            text = response.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"[{self.node_info.node_id}] Decomposition failed: {e}")
            return {did: instruction for did in drone_ids}

    # ── 区域报告生成（LLM）─────────────────────────────────────────────────

    def _generate_area_report(self, original_instruction: str, drone_reports: dict) -> str:
        """融合各执行节点报告，生成区域报告"""
        if not drone_reports:
            return "未收到任何执行节点报告。"

        if not self.llm:
            lines = [f"## 区域报告\n\n任务：{original_instruction}\n"]
            for drone_id, rdata in drone_reports.items():
                lines.append(f"### {drone_id}\n{rdata.get('report', '无报告')}\n")
            return "\n".join(lines)

        reports_text = ""
        for drone_id, rdata in drone_reports.items():
            reports_text += f"\n--- {drone_id} 报告 ---\n{rdata.get('report', '无报告')}\n"

        prompt = f"""你是区域协调员，需要将下属执行设备的报告汇总为区域报告。

区域任务：{original_instruction}

各执行设备报告：
{reports_text}

请生成区域报告，包含：
1. 区域任务执行概况
2. 各设备发现汇总
3. 区域异常/关键发现
4. 区域结论

直接输出报告内容："""

        try:
            return self.llm.chat(prompt)
        except Exception as e:
            return f"区域报告生成失败: {e}\n\n原始报告:\n{reports_text}"

    # ── 处理执行节点消息 ────────────────────────────────────────────────────────

    def _on_drone_status(self, msg: SwarmMessage) -> dict:
        """处理执行节点状态上报"""
        task_id = msg.payload.get("task_id", "")
        state = msg.payload.get("state", "")
        if task_id in self._active_tasks:
            self._active_tasks[task_id]["state"] = TaskState(state)
        logger.info(f"[{self.node_info.node_id}] Executor status: {task_id} → {state}")
        return {"status": "ok"}

    def _on_drone_report(self, msg: SwarmMessage) -> dict:
        """处理执行节点报告"""
        task_id = msg.payload.get("task_id", "")
        # 找到对应的父任务
        task_info = self._active_tasks.get(task_id, {})
        parent_task = task_info.get("parent_task", "")

        if parent_task and parent_task in self._drone_reports:
            self._drone_reports[parent_task][msg.sender_id] = msg.payload
        logger.info(f"[{self.node_info.node_id}] Executor report from {msg.sender_id}")
        return {"status": "ok"}
