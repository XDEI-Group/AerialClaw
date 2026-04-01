"""
swarm/commander.py — 主节点（Commander）

全局调度中心，本身也是一个 AerialClaw 实例。
职责：
    1. 接收任务（自然语言）
    2. 用 LLM 分解任务，按子节点管辖区域分配
    3. 收集各子节点的区域报告
    4. 用 LLM 融合生成全局报告
"""

import time
import uuid
import logging
from typing import Optional

from swarm.protocol import (
    NodeRole, NodeInfo, MessageType, TaskState, SwarmMessage,
    make_task_assign, make_task_report,
)
from swarm.node import SwarmNode

logger = logging.getLogger(__name__)


class Commander:
    """
    主节点调度器。
    
    使用方式：
        commander = Commander(port=6000, llm_client=llm)
        commander.start()
        report = commander.execute_mission("搜索整个区域，寻找被困人员")
    """

    def __init__(self, port: int = 6000, llm_client=None, node_id: str = "commander"):
        self.node_info = NodeInfo(
            node_id=node_id,
            role=NodeRole.COMMANDER,
            name="AerialClaw Commander",
            host="0.0.0.0",
            port=port,
            capabilities=["task_decomposition", "report_fusion", "resource_allocation"],
        )
        self.swarm = SwarmNode(self.node_info, parent_url=None)
        self.llm = llm_client

        # 任务追踪 {task_id → {子节点 task 信息}}
        self._tasks: dict[str, dict] = {}
        # 已收集的报告 {task_id → {child_id → report}}
        self._reports: dict[str, dict] = {}

        # 注册消息处理
        self.swarm.on(MessageType.TASK_STATUS, self._on_task_status)
        self.swarm.on(MessageType.TASK_REPORT, self._on_task_report)

    def start(self):
        """启动主节点"""
        self.swarm.start()
        logger.info(f"Commander started on port {self.node_info.port}")

    def stop(self):
        self.swarm.stop()

    # ── 任务执行 ──────────────────────────────────────────────────────────────

    def execute_mission(self, instruction: str, timeout: float = 300.0) -> str:
        """
        执行一个完整任务：分解 → 分配 → 等待 → 汇总。
        
        Args:
            instruction: 自然语言任务描述
            timeout: 任务超时（秒）
            
        Returns:
            全局汇总报告（自然语言）
        """
        mission_id = str(uuid.uuid4())[:8]
        logger.info(f"[Commander] Mission {mission_id}: {instruction}")

        # 1. 获取可用子节点
        coordinators = self.swarm.get_alive_children()
        if not coordinators:
            return "错误：没有可用的子节点。"

        # 2. LLM 分解任务
        sub_tasks = self._decompose_task(instruction, coordinators)

        # 3. 分配给各子节点
        self._reports[mission_id] = {}
        for coord_id, sub_instruction in sub_tasks.items():
            task_id = f"{mission_id}-{coord_id}"
            msg = make_task_assign(
                sender_id=self.node_info.node_id,
                receiver_id=coord_id,
                task_id=task_id,
                instruction=sub_instruction,
            )
            self.swarm.send_to_child(coord_id, msg)
            self._tasks[task_id] = {
                "mission_id": mission_id,
                "coordinator": coord_id,
                "instruction": sub_instruction,
                "state": TaskState.PENDING,
            }
            logger.info(f"[Commander] Assigned to {coord_id}: {sub_instruction[:80]}...")

        # 4. 等待所有子节点报告
        deadline = time.time() + timeout
        while time.time() < deadline:
            collected = self._reports.get(mission_id, {})
            if len(collected) >= len(sub_tasks):
                break
            time.sleep(2)

        # 5. LLM 融合全局报告
        collected = self._reports.get(mission_id, {})
        report = self._fuse_reports(instruction, collected)
        logger.info(f"[Commander] Mission {mission_id} complete. Report generated.")
        return report

    # ── 任务分解（LLM）─────────────────────────────────────────────────────

    def _decompose_task(self, instruction: str, coordinator_ids: list) -> dict:
        """
        用 LLM 将全局任务分解为子任务，分配给各子节点。
        
        Returns:
            {coordinator_id → 子任务自然语言指令}
        """
        if not self.llm:
            # 无 LLM 时平均分配
            return {cid: instruction for cid in coordinator_ids}

        # 收集各子节点的能力信息
        children_info = []
        for cid in coordinator_ids:
            child = self.swarm.children.get(cid)
            if child:
                children_info.append(f"- {cid} (名称: {child.name}, 能力: {child.capabilities}, 下属: {child.children})")

        prompt = f"""你是无人机集群的指挥官。你需要将一个任务分解为子任务，分配给不同的区域协调节点。

全局任务：{instruction}

可用的区域协调节点：
{chr(10).join(children_info)}

请为每个协调节点生成一条自然语言子任务指令。子任务应该：
1. 根据各节点管辖的无人机能力合理分配
2. 明确指定各节点负责的区域或目标
3. 包含完成标准和报告要求

请严格按如下 JSON 格式输出（不要输出其他内容）：
{{
    "{coordinator_ids[0]}": "子任务指令...",
    ...
}}"""

        try:
            response = self.llm.chat(prompt)
            import json
            # 尝试从回复中提取 JSON
            text = response.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            logger.error(f"[Commander] Task decomposition failed: {e}, falling back to broadcast")
            return {cid: instruction for cid in coordinator_ids}

    # ── 报告融合（LLM）─────────────────────────────────────────────────────

    def _fuse_reports(self, original_instruction: str, reports: dict) -> str:
        """
        用 LLM 将各子节点报告融合为全局报告。
        """
        if not reports:
            return "未收到任何子节点报告。"

        if not self.llm:
            # 无 LLM 时简单拼接
            lines = [f"## 全局任务报告\n\n原始任务：{original_instruction}\n"]
            for coord_id, report_data in reports.items():
                lines.append(f"### {coord_id} 报告\n{report_data.get('report', '无报告')}\n")
            return "\n".join(lines)

        reports_text = ""
        for coord_id, report_data in reports.items():
            reports_text += f"\n--- {coord_id} 的区域报告 ---\n{report_data.get('report', '无报告')}\n"

        prompt = f"""你是无人机集群的指挥官。各区域协调节点已完成任务并提交了区域报告，你需要将它们融合为一份完整的全局任务报告。

原始任务：{original_instruction}

各节点报告：
{reports_text}

请生成一份结构化的全局报告，包含：
1. 任务概述
2. 各区域执行情况汇总
3. 关键发现
4. 总体结论

直接输出报告内容："""

        try:
            return self.llm.chat(prompt)
        except Exception as e:
            logger.error(f"[Commander] Report fusion failed: {e}")
            return f"报告融合失败: {e}\n\n原始报告:\n{reports_text}"

    # ── 消息处理回调 ──────────────────────────────────────────────────────────

    def _on_task_status(self, msg: SwarmMessage) -> dict:
        """处理子节点的任务状态上报"""
        task_id = msg.payload.get("task_id", "")
        state = msg.payload.get("state", "")
        progress = msg.payload.get("progress", "")
        if task_id in self._tasks:
            self._tasks[task_id]["state"] = TaskState(state)
        logger.info(f"[Commander] Task {task_id} status: {state} - {progress}")
        return {"status": "ok"}

    def _on_task_report(self, msg: SwarmMessage) -> dict:
        """处理子节点提交的任务报告"""
        task_id = msg.payload.get("task_id", "")
        task_info = self._tasks.get(task_id, {})
        mission_id = task_info.get("mission_id", task_id.split("-")[0])

        if mission_id not in self._reports:
            self._reports[mission_id] = {}
        self._reports[mission_id][msg.sender_id] = msg.payload
        logger.info(f"[Commander] Report received from {msg.sender_id} for task {task_id}")
        return {"status": "ok"}
