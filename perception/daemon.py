"""
perception/daemon.py
感知守护线程 (Perception Daemon)

第一层感知: 后台持续运行, 每隔几秒自动处理传感器数据,
输出环境摘要字符串 (~100 tokens), LLM 每次规划时自动获取。

功能:
  - LiDAR -> 方位障碍物描述 ("前方 24.5m 有建筑物")
  - 状态 -> 一句话摘要 ("高度 5.0m, 电池 87%, 悬停中")
  - 多摄像头方位感知 (粗略角度推算)
  - 融合摘要: 将 LiDAR + 状态 + VLM 分析合并为统一环境描述

设计:
  - 不直接给 LLM 原始数据, 只给语义化摘要
  - 每次摘要 ~100 tokens, 控制 LLM context 开销
  - VLM 深度分析按需触发, 不在每次循环中调用
"""

import math
import time
import threading
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


# ── 方位定义 ─────────────────────────────────────────────────────────────────

# LiDAR 角度 -> 方位描述
# LiDAR 0° = 正前方, 顺时针为正
DIRECTION_SECTORS = [
    (-22.5,  22.5,  "正前方"),
    ( 22.5,  67.5,  "右前方"),
    ( 67.5, 112.5,  "正右方"),
    (112.5, 157.5,  "右后方"),
    (157.5, 180.0,  "正后方"),
    (-180.0, -157.5, "正后方"),
    (-157.5, -112.5, "左后方"),
    (-112.5, -67.5,  "正左方"),
    (-67.5, -22.5,   "左前方"),
]

# 摄像头方位 -> 角度中心 (与 LiDAR 坐标系对齐)
CAMERA_DIRECTIONS = {
    "front": 0.0,
    "right": 90.0,
    "rear":  180.0,
    "left":  -90.0,
}

# 摄像头 FOV (度)
CAMERA_FOV = 80.0


def _angle_to_direction(angle_deg: float) -> str:
    """将角度转为方位描述。"""
    # 规范化到 [-180, 180)
    angle_deg = ((angle_deg + 180) % 360) - 180
    for lo, hi, name in DIRECTION_SECTORS:
        if lo <= angle_deg < hi:
            return name
    return "未知方向"


def _camera_covers_angle(camera_dir: str, angle_deg: float) -> bool:
    """检查某个角度是否在指定摄像头的 FOV 范围内。"""
    cam_center = CAMERA_DIRECTIONS.get(camera_dir)
    if cam_center is None:
        return False
    half_fov = CAMERA_FOV / 2.0
    # 规范化角度差到 [-180, 180)
    diff = ((angle_deg - cam_center + 180) % 360) - 180
    return abs(diff) <= half_fov


class PerceptionDaemon:
    """
    感知守护线程。
    后台持续运行, 周期性生成环境摘要。
    """

    def __init__(
        self,
        sensor_bridge=None,
        adapter=None,
        update_interval: float = 3.0,
    ):
        """
        Args:
            sensor_bridge: GzSensorBridge 实例 (提供 LiDAR / 摄像头数据)
            adapter:       SimAdapter 实例 (提供位置/电池/状态)
            update_interval: 摘要更新间隔 (秒)
        """
        self._sensor_bridge = sensor_bridge
        self._adapter = adapter
        self._interval = update_interval

        # 当前环境摘要
        self._summary_lock = threading.Lock()
        self._summary: str = "(感知系统启动中...)"
        self._summary_ts: float = 0.0

        # 分段摘要 (供单独查询)
        self._lidar_summary: str = ""
        self._state_summary: str = ""
        self._vlm_summary: str = ""  # VLM 分析结果 (按需填充)

        # 后台线程
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ── 生命周期 ──────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """启动感知守护线程。"""
        if self._running:
            return True
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="perception-daemon"
        )
        self._thread.start()
        logger.info("感知守护线程已启动 (间隔 %.1fs)", self._interval)
        return True

    def stop(self):
        """停止感知守护线程。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("感知守护线程已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 外部接口 ──────────────────────────────────────────────────────────────

    def get_summary(self) -> str:
        """获取当前环境摘要 (线程安全)。供 planner system prompt 注入。"""
        with self._summary_lock:
            return self._summary

    def get_detailed_summary(self) -> Dict[str, str]:
        """获取分段摘要 (线程安全)。"""
        with self._summary_lock:
            return {
                "lidar": self._lidar_summary,
                "state": self._state_summary,
                "vlm": self._vlm_summary,
                "combined": self._summary,
                "timestamp": self._summary_ts,
            }

    def set_vlm_summary(self, summary: str):
        """外部注入 VLM 分析结果 (由 vlm_analyzer 调用)。"""
        with self._summary_lock:
            self._vlm_summary = summary

    def update_refs(self, sensor_bridge=None, adapter=None):
        """更新传感器桥接和适配器引用 (延迟初始化场景)。"""
        if sensor_bridge is not None:
            self._sensor_bridge = sensor_bridge
        if adapter is not None:
            self._adapter = adapter

    # ── 主循环 ────────────────────────────────────────────────────────────────

    def _loop(self):
        """后台循环: 周期性生成环境摘要。"""
        while self._running:
            try:
                self._update_summary()
            except Exception as e:
                logger.warning("感知摘要更新异常: %s", e)
            time.sleep(self._interval)

    def _update_summary(self):
        """执行一次摘要更新。"""
        parts = []

        # 1. 状态摘要
        state_str = self._build_state_summary()
        if state_str:
            parts.append(state_str)

        # 2. LiDAR 摘要
        lidar_str = self._build_lidar_summary()
        if lidar_str:
            parts.append(lidar_str)

        # 3. VLM 摘要 (如果有)
        vlm_str = self._vlm_summary
        if vlm_str:
            parts.append(f"视觉分析: {vlm_str}")

        combined = " | ".join(parts) if parts else "(传感器离线, 无环境数据)"

        with self._summary_lock:
            self._lidar_summary = lidar_str
            self._state_summary = state_str
            self._summary = combined
            self._summary_ts = time.time()

    # ── 状态摘要 ──────────────────────────────────────────────────────────────

    def _build_state_summary(self) -> str:
        """从 adapter 获取飞行状态, 生成一句话摘要。"""
        if not self._adapter:
            return ""
        try:
            if not self._adapter.is_connected():
                return "适配器离线"

            pos = self._adapter.get_position()
            bat = self._adapter.get_battery()
            in_air = self._adapter.is_in_air()
            armed = self._adapter.is_armed()

            altitude = round(-pos.down, 1)
            # bat = (voltage, remaining_fraction 0-1)
            # remaining fraction: bat[1] in [0,1]
            bat_pct = round(bat[1] * 100) if bat else 0
            status = "飞行中" if in_air else ("地面待命" if armed else "地面锁定")

            return f"高度{altitude}m, 电池{bat_pct}%, {status}, 位置NED({round(pos.north,1)},{round(pos.east,1)},{round(pos.down,1)})"
        except Exception as e:
            logger.debug("状态摘要获取失败: %s", e)
            return "状态获取失败"

    # ── LiDAR 摘要 ────────────────────────────────────────────────────────────

    def _build_lidar_summary(self) -> str:
        """
        将 LiDAR 扫描数据转为方位障碍物描述。

        粗略对齐逻辑:
          - 将 360° LiDAR 扫描按 8 方位分区
          - 每个方位取最近障碍物距离
          - 检查该方位是否有摄像头覆盖 → 标注 [视觉可见] 或 [仅雷达]
          - 只报告有意义的障碍物 (距离 < range_max * 0.9)

        输出格式:
          "障碍物: 前方24.5m[视觉可见], 左方18.2m[仅雷达], 其余方向>30m"
        """
        if not self._sensor_bridge:
            return ""
        try:
            scan = self._sensor_bridge.get_lidar_scan()
            if scan is None:
                return ""

            ranges = scan["ranges"]
            angle_min = scan["angle_min"]
            angle_inc = scan["angle_increment"]
            range_min = scan["range_min"]
            range_max = scan["range_max"]

            # 按方位分区统计最近障碍物
            sector_min: Dict[str, float] = {}
            sector_angle: Dict[str, float] = {}  # 记录最近障碍物的角度

            for i, r in enumerate(ranges):
                if not math.isfinite(r) or r < range_min or r >= range_max:
                    continue
                angle_deg = math.degrees(angle_min + i * angle_inc)
                direction = _angle_to_direction(angle_deg)
                if direction not in sector_min or r < sector_min[direction]:
                    sector_min[direction] = r
                    sector_angle[direction] = angle_deg

            if not sector_min:
                return "障碍物: 四周无障碍物(>30m)"

            # 生成描述
            obstacle_parts = []
            for direction, dist in sorted(sector_min.items(), key=lambda x: x[1]):
                angle = sector_angle[direction]
                # 检查是否有摄像头覆盖此方位
                cam_covered = any(
                    _camera_covers_angle(cam_dir, angle)
                    for cam_dir in CAMERA_DIRECTIONS
                )
                tag = "[视觉+雷达]" if cam_covered else "[仅雷达]"
                obstacle_parts.append(f"{direction}{round(dist, 1)}m{tag}")

            # 限制描述长度 (最多 4 个方位)
            if len(obstacle_parts) > 4:
                obstacle_parts = obstacle_parts[:4]
                obstacle_parts.append("...")

            return "障碍物: " + ", ".join(obstacle_parts)
        except Exception as e:
            logger.debug("LiDAR 摘要生成失败: %s", e)
            return ""


# ── 全局单例 ──────────────────────────────────────────────────────────────────

_daemon: Optional[PerceptionDaemon] = None


def get_daemon() -> Optional[PerceptionDaemon]:
    """获取全局感知守护线程实例。"""
    return _daemon


def init_daemon(
    sensor_bridge=None,
    adapter=None,
    update_interval: float = 3.0,
) -> PerceptionDaemon:
    """初始化并启动全局感知守护线程。"""
    global _daemon
    if _daemon is not None:
        _daemon.stop()
    _daemon = PerceptionDaemon(
        sensor_bridge=sensor_bridge,
        adapter=adapter,
        update_interval=update_interval,
    )
    _daemon.start()
    return _daemon
