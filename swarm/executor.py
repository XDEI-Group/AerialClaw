"""
swarm/executor.py — 执行节点（Executor）

最底层节点，每个执行设备运行一个。
职责：
    1. 向子节点注册（上报自身能力）
    2. 接收子节点的自然语言任务指令
    3. 调用本机 AerialClaw 的 AgentLoop 执行任务
    4. 执行完成后生成报告上报子节点

关键：Executor 不需要改动现有 AerialClaw 代码。
它只是一层薄封装，把集群消息翻译成 AgentLoop 的输入。
"""

import time
import uuid
import logging
import threading
from typing import Optional

from swarm.protocol import (
    NodeRole, NodeInfo, MessageType, TaskState, SwarmMessage,
    make_task_status, make_task_report,
)
from swarm.node import SwarmNode

logger = logging.getLogger(__name__)


class Executor:
    """
    设备执行节点。
    
    包装现有 AerialClaw 的 AgentLoop，接入集群通信。
    
    使用方式：
        executor = Executor(
            port=6200,
            coordinator_url="http://coordinator-host:6100",
            agent_loop=my_agent_loop,   # 现有的 AgentLoop 实例
            capabilities=["camera_5x", "lidar_2d", "search", "patrol"],
        )
        executor.start()
    """

    def __init__(self, port: int = 6200, coordinator_url: str = "http://localhost:6100",
                 agent_loop=None, capabilities: list = None,
                 node_id: str = None, name: str = "UAV"):
        self.node_info = NodeInfo(
            node_id=node_id or f"uav-{str(uuid.uuid4())[:4]}",
            role=NodeRole.EXECUTOR,
            name=name,
            host="0.0.0.0",
            port=port,
            capabilities=capabilities or ["flight", "camera", "lidar"],
        )
        self.coordinator_url = coordinator_url
        self.swarm = SwarmNode(self.node_info, parent_url=coordinator_url)
        self.agent_loop = agent_loop  # 现有 AerialClaw AgentLoop

        # 当前任务
        self._current_task_id: Optional[str] = None
        self._is_executing: bool = False

        # 注册消息处理
        self.swarm.on(MessageType.TASK_ASSIGN, self._on_task_assign)

    def start(self):
        """启动执行节点"""
        self.swarm.start()
        logger.info(f"Executor '{self.node_info.name}' ({self.node_info.node_id}) "
                     f"started on port {self.node_info.port}")

    def stop(self):
        self.swarm.stop()

    # ── 接收任务 ──────────────────────────────────────────────────────────────

    def _on_task_assign(self, msg: SwarmMessage) -> dict:
        """收到子节点分配的任务"""
        task_id = msg.payload.get("task_id", "")
        instruction = msg.payload.get("instruction", "")

        if self._is_executing:
            logger.warning(f"[{self.node_info.node_id}] Busy, rejecting task {task_id}")
            return {"status": "busy", "task_id": task_id}

        logger.info(f"[{self.node_info.node_id}] Received task {task_id}: {instruction[:80]}...")

        # 上报开始执行
        self._current_task_id = task_id
        self._is_executing = True
        status_msg = make_task_status(self.node_info.node_id, task_id,
                                       TaskState.IN_PROGRESS, "开始执行任务")
        self.swarm.send(self.coordinator_url, status_msg)

        # 在新线程中执行
        t = threading.Thread(target=self._execute_flight, args=(task_id, instruction), daemon=True)
        t.start()
        return {"status": "accepted", "task_id": task_id}

    def _execute_flight(self, task_id: str, instruction: str):
        """执行任务"""
        try:
            report_text = ""

            if self.agent_loop:
                # 调用现有 AerialClaw AgentLoop
                # AgentLoop.run() 接收自然语言指令，返回执行结果
                result = self._run_agent_loop(instruction)
                report_text = result
            else:
                # 无 AgentLoop 时模拟执行
                logger.info(f"[{self.node_info.node_id}] Simulating task: {instruction[:60]}...")
                time.sleep(5)  # 模拟执行时间
                report_text = (
                    f"[{self.node_info.name}] 已完成任务。\n"
                    f"任务指令：{instruction}\n"
                    f"执行结果：模拟执行完成，未发现异常。"
                )

            # 上报任务报告
            report_msg = make_task_report(
                sender_id=self.node_info.node_id,
                task_id=task_id,
                report=report_text,
            )
            self.swarm.send(self.coordinator_url, report_msg)

            # 上报完成状态
            status_msg = make_task_status(self.node_info.node_id, task_id,
                                           TaskState.COMPLETED, "任务完成")
            self.swarm.send(self.coordinator_url, status_msg)

        except Exception as e:
            logger.error(f"[{self.node_info.node_id}] Task {task_id} failed: {e}")
            status_msg = make_task_status(self.node_info.node_id, task_id,
                                           TaskState.FAILED, str(e))
            self.swarm.send(self.coordinator_url, status_msg)
        finally:
            self._is_executing = False
            self._current_task_id = None

    def _run_agent_loop(self, instruction: str) -> str:
        """
        调用 AerialClaw AgentLoop 执行任务。
        
        这里对接现有的 brain/agent_loop.py，
        把集群的自然语言指令喂给单机 AI 决策循环。
        """
        try:
            # agent_loop.execute_task() 是现有接口
            # 它接收自然语言指令，自主执行，返回报告
            if hasattr(self.agent_loop, 'execute_task'):
                result = self.agent_loop.execute_task(instruction)
                if isinstance(result, dict):
                    return result.get("report", str(result))
                return str(result)
            elif hasattr(self.agent_loop, 'run'):
                result = self.agent_loop.run(instruction)
                return str(result)
            else:
                return f"AgentLoop 没有可用的执行接口"
        except Exception as e:
            logger.error(f"[{self.node_info.node_id}] AgentLoop error: {e}")
            return f"执行出错: {e}"

    # ── 状态查询 ──────────────────────────────────────────────────────────────

    @property
    def is_busy(self) -> bool:
        return self._is_executing

    @property
    def current_task(self) -> Optional[str]:
        return self._current_task_id
