"""
swarm/protocol.py — 节点间通信协议

定义三级架构中所有节点的通信消息格式。
所有消息统一走 JSON，通过 REST 或 WebSocket 传输。

消息类型：
    REGISTER        — 下级节点向上级注册
    HEARTBEAT       — 心跳保活
    TASK_ASSIGN     — 上级向下级分配任务（自然语言）
    TASK_STATUS     — 下级上报任务状态
    TASK_REPORT     — 下级提交任务报告
    QUERY_STATUS    — 上级查询下级状态
    STATUS_RESPONSE — 下级响应状态查询
"""

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any


class NodeRole(str, Enum):
    """节点角色"""
    COMMANDER = "commander"       # 主节点
    COORDINATOR = "coordinator"   # 子节点
    EXECUTOR = "executor"         # 无人机执行节点


class MessageType(str, Enum):
    """消息类型"""
    REGISTER = "register"
    HEARTBEAT = "heartbeat"
    TASK_ASSIGN = "task_assign"
    TASK_STATUS = "task_status"
    TASK_REPORT = "task_report"
    QUERY_STATUS = "query_status"
    STATUS_RESPONSE = "status_response"


class TaskState(str, Enum):
    """任务状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class NodeInfo:
    """节点身份信息（注册时上报）"""
    node_id: str                          # 唯一标识
    role: NodeRole                        # 角色
    name: str = ""                        # 可读名称
    host: str = ""                        # IP/hostname
    port: int = 0                         # 服务端口
    capabilities: list = field(default_factory=list)  # 能力列表（来自 BODY.md/SKILLS.md）
    children: list = field(default_factory=list)       # 下属节点 ID 列表

    def to_dict(self) -> dict:
        d = asdict(self)
        d["role"] = self.role.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "NodeInfo":
        d["role"] = NodeRole(d["role"])
        return cls(**d)


@dataclass
class SwarmMessage:
    """通信消息"""
    msg_type: MessageType
    sender_id: str                         # 发送者节点 ID
    receiver_id: str = ""                  # 接收者节点 ID（空=广播）
    payload: dict = field(default_factory=dict)
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "msg_type": self.msg_type.value,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "payload": self.payload,
            "msg_id": self.msg_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SwarmMessage":
        d["msg_type"] = MessageType(d["msg_type"])
        return cls(**d)


# ── 便捷消息构造 ─────────────────────────────────────────────────────────────

def make_register(node_info: NodeInfo) -> SwarmMessage:
    """构造注册消息"""
    return SwarmMessage(
        msg_type=MessageType.REGISTER,
        sender_id=node_info.node_id,
        payload=node_info.to_dict(),
    )


def make_heartbeat(node_id: str, status: dict = None) -> SwarmMessage:
    """构造心跳消息"""
    return SwarmMessage(
        msg_type=MessageType.HEARTBEAT,
        sender_id=node_id,
        payload=status or {},
    )


def make_task_assign(sender_id: str, receiver_id: str, task_id: str,
                     instruction: str, area: dict = None) -> SwarmMessage:
    """构造任务分配消息（自然语言指令）"""
    return SwarmMessage(
        msg_type=MessageType.TASK_ASSIGN,
        sender_id=sender_id,
        receiver_id=receiver_id,
        payload={
            "task_id": task_id,
            "instruction": instruction,    # 自然语言任务描述
            "area": area or {},            # 分配的区域（可选）
        },
    )


def make_task_status(sender_id: str, task_id: str, state: TaskState,
                     progress: str = "") -> SwarmMessage:
    """构造任务状态上报"""
    return SwarmMessage(
        msg_type=MessageType.TASK_STATUS,
        sender_id=sender_id,
        payload={
            "task_id": task_id,
            "state": state.value,
            "progress": progress,
        },
    )


def make_task_report(sender_id: str, task_id: str, report: str,
                     findings: list = None) -> SwarmMessage:
    """构造任务报告"""
    return SwarmMessage(
        msg_type=MessageType.TASK_REPORT,
        sender_id=sender_id,
        payload={
            "task_id": task_id,
            "report": report,              # 自然语言报告
            "findings": findings or [],    # 结构化发现列表
        },
    )
