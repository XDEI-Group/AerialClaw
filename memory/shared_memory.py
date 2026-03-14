"""
memory/shared_memory.py — AerialClaw 跨设备共享记忆池

设计：
  共享池 — 环境地图、目标位置、危险区域、广播发现（所有设备可读写）
  私有池 — 各设备技能参数、任务历史（仅所属设备读写）

线程安全；支持 device_manager 回调广播（可选）。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from core.errors import MemoryStoreError, MemoryRetrievalError
from core.logger import get_logger

logger = get_logger("memory.shared_memory")


# ── 广播事件 ─────────────────────────────────────────────────

class DiscoveryEvent:
    """广播发现事件"""

    def __init__(self, discovery: str, source_device: str, timestamp: float):
        self.discovery = discovery
        self.source_device = source_device
        self.timestamp = timestamp

    def __repr__(self) -> str:
        return (
            f"DiscoveryEvent(source={self.source_device!r}, "
            f"discovery={self.discovery[:40]!r})"
        )


# ── 共享记忆池 ────────────────────────────────────────────────

class SharedMemory:
    """
    多设备共享记忆池。

    共享池（所有设备）：环境地图、目标位置、危险区域、广播发现。
    私有池（各设备）：技能参数、任务历史等本地数据。

    Args:
        device_manager: 可选。若传入，广播时调用
                        device_manager.broadcast(event) 通知各设备。
    """

    def __init__(self, device_manager: Optional[Any] = None):
        self._device_manager = device_manager

        # 共享池：key → value
        self._shared: Dict[str, Any] = {}
        self._shared_lock = threading.RLock()

        # 私有池：device_id → {key → value}
        self._private: Dict[str, Dict[str, Any]] = {}
        self._private_lock = threading.RLock()

        # 广播历史（按时间顺序，方便回放）
        self._discoveries: List[DiscoveryEvent] = []
        self._discovery_lock = threading.Lock()

        # 外部订阅者 list[Callable[[DiscoveryEvent], None]]
        self._subscribers: List[Callable[[DiscoveryEvent], None]] = []
        self._sub_lock = threading.Lock()

        logger.info("SharedMemory 初始化（共享池 + 私有池）")

    # ── 共享池 ────────────────────────────────────────────────

    def share(self, key: str, value: Any, source_device: str) -> None:
        """
        将数据写入共享池，所有设备可见。

        Args:
            key:           数据键名（如 "env_map"、"target_pos"）
            value:         数据值（任意可序列化对象）
            source_device: 写入来源设备 ID

        Raises:
            MemoryStoreError: 写入失败时
        """
        try:
            with self._shared_lock:
                self._shared[key] = {
                    "value": value,
                    "source": source_device,
                    "updated_at": time.time(),
                }
            logger.debug(f"[share] [{source_device}] {key} = {str(value)[:60]}")
        except Exception as e:
            raise MemoryStoreError(
                f"共享记忆写入失败：{e}",
                fix_hint="检查数据是否可序列化",
            ) from e

    def get_shared(self, key: str) -> Any:
        """
        读取共享池指定键的值。

        Args:
            key: 数据键名

        Returns:
            存储的值；键不存在时返回 None

        Raises:
            MemoryRetrievalError: 读取失败时
        """
        try:
            with self._shared_lock:
                entry = self._shared.get(key)
            return entry["value"] if entry is not None else None
        except Exception as e:
            raise MemoryRetrievalError(f"共享记忆读取失败：{e}") from e

    def get_all_shared(self) -> Dict[str, Any]:
        """
        返回共享池全部数据的快照。

        Returns:
            {key: value} 字典（不含元数据）
        """
        try:
            with self._shared_lock:
                return {k: v["value"] for k, v in self._shared.items()}
        except Exception as e:
            raise MemoryRetrievalError(f"共享记忆全量读取失败：{e}") from e

    def delete_shared(self, key: str) -> None:
        """从共享池删除指定键。"""
        with self._shared_lock:
            removed = self._shared.pop(key, None)
        if removed is not None:
            logger.debug(f"[delete_shared] 已删除 key={key!r}")

    # ── 私有池 ────────────────────────────────────────────────

    def set_private(self, device_id: str, key: str, value: Any) -> None:
        """
        写入设备私有记忆。

        Args:
            device_id: 设备 ID
            key:       数据键名
            value:     数据值

        Raises:
            MemoryStoreError: 写入失败时
        """
        try:
            with self._private_lock:
                if device_id not in self._private:
                    self._private[device_id] = {}
                self._private[device_id][key] = {
                    "value": value,
                    "updated_at": time.time(),
                }
            logger.debug(f"[set_private] [{device_id}] {key} = {str(value)[:60]}")
        except Exception as e:
            raise MemoryStoreError(f"私有记忆写入失败：{e}") from e

    def get_private(self, device_id: str, key: str) -> Any:
        """
        读取设备私有记忆。

        Args:
            device_id: 设备 ID
            key:       数据键名

        Returns:
            存储的值；不存在时返回 None
        """
        try:
            with self._private_lock:
                device_store = self._private.get(device_id, {})
                entry = device_store.get(key)
            return entry["value"] if entry is not None else None
        except Exception as e:
            raise MemoryRetrievalError(f"私有记忆读取失败：{e}") from e

    def get_all_private(self, device_id: str) -> Dict[str, Any]:
        """
        返回指定设备私有记忆的全量快照。

        Args:
            device_id: 设备 ID

        Returns:
            {key: value} 字典
        """
        try:
            with self._private_lock:
                device_store = self._private.get(device_id, {})
                return {k: v["value"] for k, v in device_store.items()}
        except Exception as e:
            raise MemoryRetrievalError(f"私有记忆全量读取失败：{e}") from e

    def delete_private(self, device_id: str, key: str) -> None:
        """删除设备私有记忆中的指定键。"""
        with self._private_lock:
            if device_id in self._private:
                self._private[device_id].pop(key, None)

    # ── 广播发现 ──────────────────────────────────────────────

    def broadcast_discovery(self, discovery: str, source_device: str) -> None:
        """
        广播发现事件，所有设备（及订阅者）均可感知。

        典型用途：无人机发现目标、危险区域、地标等。
        发现会写入共享池（discoveries 列表）并触发订阅者回调。

        Args:
            discovery:     发现内容描述
            source_device: 来源设备 ID

        Raises:
            MemoryStoreError: 记录失败时
        """
        try:
            event = DiscoveryEvent(
                discovery=discovery,
                source_device=source_device,
                timestamp=time.time(),
            )

            # 记录到历史列表
            with self._discovery_lock:
                self._discoveries.append(event)

            # 同步到共享池（最新发现）
            self.share("latest_discovery", {
                "text": discovery,
                "source": source_device,
                "timestamp": event.timestamp,
            }, source_device)

            logger.info(f"[broadcast] [{source_device}] {discovery[:80]}")

            # 通知外部订阅者
            with self._sub_lock:
                subscribers = list(self._subscribers)
            for cb in subscribers:
                try:
                    cb(event)
                except Exception as cb_err:
                    logger.warning(f"[broadcast] 订阅者回调异常：{cb_err}")

            # 通知 device_manager（若提供）
            if self._device_manager is not None:
                try:
                    if hasattr(self._device_manager, "broadcast"):
                        self._device_manager.broadcast(event)
                except Exception as dm_err:
                    logger.warning(f"[broadcast] device_manager 通知失败：{dm_err}")

        except MemoryStoreError:
            raise
        except Exception as e:
            raise MemoryStoreError(f"广播发现记录失败：{e}") from e

    def get_discoveries(
        self,
        source_device: Optional[str] = None,
        since: Optional[float] = None,
    ) -> List[DiscoveryEvent]:
        """
        查询广播发现历史。

        Args:
            source_device: 若指定，只返回该设备的发现
            since:         若指定，只返回该时间戳之后的发现

        Returns:
            满足条件的 DiscoveryEvent 列表（按时间升序）
        """
        with self._discovery_lock:
            items = list(self._discoveries)

        if source_device is not None:
            items = [e for e in items if e.source_device == source_device]
        if since is not None:
            items = [e for e in items if e.timestamp >= since]
        return items

    # ── 订阅 ──────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[DiscoveryEvent], None]) -> None:
        """
        注册广播事件订阅者。

        Args:
            callback: 接收 DiscoveryEvent 的可调用对象
        """
        with self._sub_lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)
                logger.debug(f"[subscribe] 已注册订阅者 {callback!r}")

    def unsubscribe(self, callback: Callable[[DiscoveryEvent], None]) -> None:
        """注销广播事件订阅者。"""
        with self._sub_lock:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

    # ── 统计 ──────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """返回当前记忆池统计摘要。"""
        with self._shared_lock:
            shared_keys = list(self._shared.keys())
        with self._private_lock:
            private_counts = {did: len(store) for did, store in self._private.items()}
        with self._discovery_lock:
            n_discoveries = len(self._discoveries)
        return {
            "shared_keys": shared_keys,
            "shared_count": len(shared_keys),
            "private_devices": private_counts,
            "discoveries": n_discoveries,
        }
