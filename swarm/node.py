"""
swarm/node.py — 节点通信服务

每个 AerialClaw 实例（无论是主节点、子节点还是无人机）都运行一个 SwarmNode，
负责：
    - 向上级注册
    - 接收和处理消息
    - 向下级发送指令
    - 心跳保活

基于 Flask + requests 实现，复用 AerialClaw 已有的 Web 技术栈。
"""

import time
import logging
import threading
import requests
from typing import Optional, Callable
from flask import Flask, jsonify, request as flask_request

from swarm.protocol import (
    NodeRole, NodeInfo, SwarmMessage, MessageType, TaskState,
    make_register, make_heartbeat,
)

logger = logging.getLogger(__name__)


class SwarmNode:
    """
    集群节点通信服务。
    
    每个 AerialClaw 实例启动一个 SwarmNode：
        - Commander: 监听子节点注册，分发任务，收集报告
        - Coordinator: 向 Commander 注册，管理下属无人机，汇总区域报告
        - Executor: 向 Coordinator 注册，接收并执行任务
    """

    def __init__(self, node_info: NodeInfo, parent_url: str = None):
        """
        Args:
            node_info: 本节点身份信息
            parent_url: 上级节点 URL（Commander 没有上级，传 None）
        """
        self.info = node_info
        self.parent_url = parent_url

        # 下级节点注册表 {node_id → NodeInfo}
        self.children: dict[str, NodeInfo] = {}
        # 下级节点最后心跳时间 {node_id → timestamp}
        self._heartbeats: dict[str, float] = {}

        # 消息处理回调 {MessageType → handler(SwarmMessage) → dict}
        self._handlers: dict[MessageType, Callable] = {}

        # 内部 Flask app（独立于主 server.py）
        self._app = Flask(f"swarm-{node_info.node_id}")
        self._setup_routes()

        # 心跳线程
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ── 消息处理注册 ─────────────────────────────────────────────────────────

    def on(self, msg_type: MessageType, handler: Callable):
        """注册消息处理回调"""
        self._handlers[msg_type] = handler

    # ── Flask 路由 ────────────────────────────────────────────────────────────

    def _setup_routes(self):
        app = self._app

        @app.route("/agent/identity", methods=["GET"])
        def get_identity():
            return jsonify(self.info.to_dict())

        @app.route("/agent/message", methods=["POST"])
        def receive_message():
            data = flask_request.get_json(force=True)
            msg = SwarmMessage.from_dict(data)
            return jsonify(self._dispatch(msg))

        @app.route("/agent/children", methods=["GET"])
        def list_children():
            return jsonify({
                nid: {**info.to_dict(), "last_heartbeat": self._heartbeats.get(nid, 0)}
                for nid, info in self.children.items()
            })

        @app.route("/agent/health", methods=["GET"])
        def health():
            return jsonify({"status": "ok", "node_id": self.info.node_id,
                            "role": self.info.role.value,
                            "children_count": len(self.children)})

    def _dispatch(self, msg: SwarmMessage) -> dict:
        """分发消息到对应 handler"""

        # 注册消息：统一处理
        if msg.msg_type == MessageType.REGISTER:
            child_info = NodeInfo.from_dict(msg.payload)
            self.children[child_info.node_id] = child_info
            self._heartbeats[child_info.node_id] = time.time()
            logger.info(f"[{self.info.node_id}] Node registered: {child_info.node_id} ({child_info.role.value})")
            # 也调用用户 handler（如果有）
            if MessageType.REGISTER in self._handlers:
                self._handlers[MessageType.REGISTER](msg)
            return {"status": "registered", "node_id": child_info.node_id}

        # 心跳消息
        if msg.msg_type == MessageType.HEARTBEAT:
            self._heartbeats[msg.sender_id] = time.time()
            return {"status": "ok"}

        # 其他消息：调用注册的 handler
        handler = self._handlers.get(msg.msg_type)
        if handler:
            try:
                result = handler(msg)
                return result if isinstance(result, dict) else {"status": "ok"}
            except Exception as e:
                logger.error(f"[{self.info.node_id}] Handler error for {msg.msg_type}: {e}")
                return {"status": "error", "message": str(e)}
        else:
            logger.warning(f"[{self.info.node_id}] No handler for {msg.msg_type.value}")
            return {"status": "no_handler", "msg_type": msg.msg_type.value}

    # ── 发送消息 ──────────────────────────────────────────────────────────────

    def send(self, target_url: str, msg: SwarmMessage, timeout: float = 10.0) -> dict:
        """向目标节点发送消息"""
        try:
            resp = requests.post(
                f"{target_url}/agent/message",
                json=msg.to_dict(),
                timeout=timeout,
            )
            return resp.json()
        except Exception as e:
            logger.error(f"[{self.info.node_id}] Send to {target_url} failed: {e}")
            return {"status": "error", "message": str(e)}

    def send_to_child(self, child_id: str, msg: SwarmMessage, timeout: float = 10.0) -> dict:
        """向指定下级节点发送消息"""
        child = self.children.get(child_id)
        if not child:
            return {"status": "error", "message": f"Unknown child: {child_id}"}
        url = f"http://{child.host}:{child.port}"
        msg.receiver_id = child_id
        return self.send(url, msg, timeout)

    def broadcast_to_children(self, msg: SwarmMessage) -> dict:
        """向所有下级节点广播消息"""
        results = {}
        for child_id in self.children:
            results[child_id] = self.send_to_child(child_id, msg)
        return results

    # ── 向上级注册 ────────────────────────────────────────────────────────────

    def register_to_parent(self) -> bool:
        """向上级节点注册自己"""
        if not self.parent_url:
            logger.info(f"[{self.info.node_id}] No parent (top-level node)")
            return True

        msg = make_register(self.info)
        result = self.send(self.parent_url, msg)
        if result.get("status") == "registered":
            logger.info(f"[{self.info.node_id}] Registered to parent at {self.parent_url}")
            return True
        else:
            logger.error(f"[{self.info.node_id}] Registration failed: {result}")
            return False

    # ── 心跳 ──────────────────────────────────────────────────────────────────

    def _heartbeat_loop(self, interval: float = 10.0):
        """定期向上级发送心跳"""
        while not self._stop_event.is_set():
            if self.parent_url:
                status = {
                    "children_count": len(self.children),
                    "role": self.info.role.value,
                }
                msg = make_heartbeat(self.info.node_id, status)
                self.send(self.parent_url, msg, timeout=5.0)
            self._stop_event.wait(interval)

    def get_alive_children(self, timeout_sec: float = 30.0) -> list:
        """获取存活的下级节点列表"""
        now = time.time()
        return [
            nid for nid, last in self._heartbeats.items()
            if (now - last) < timeout_sec
        ]

    # ── 启动/停止 ─────────────────────────────────────────────────────────────

    def start(self, heartbeat_interval: float = 10.0):
        """启动节点通信服务（非阻塞）"""
        # 启动 Flask 服务
        self._server_thread = threading.Thread(
            target=lambda: self._app.run(
                host="0.0.0.0", port=self.info.port, threaded=True, use_reloader=False
            ),
            daemon=True,
        )
        self._server_thread.start()
        logger.info(f"[{self.info.node_id}] Swarm node listening on port {self.info.port}")

        # 向上级注册
        time.sleep(1)  # 等 Flask 就绪
        self.register_to_parent()

        # 启动心跳
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, args=(heartbeat_interval,), daemon=True
        )
        self._heartbeat_thread.start()

    def stop(self):
        """停止节点"""
        self._stop_event.set()
        logger.info(f"[{self.info.node_id}] Swarm node stopped")
