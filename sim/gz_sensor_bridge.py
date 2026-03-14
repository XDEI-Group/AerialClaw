"""
gz_sensor_bridge.py
Gazebo Harmonic 传感器数据桥接 — 订阅 4× 相机 + 2D 激光雷达。

Topic 格式 (merge='true'):
  /world/{world}/model/{model}/link/{cam_link}/sensor/{sensor}/image
  /world/{world}/model/{model}/link/link/sensor/lidar_2d_v2/scan

Author: AerialClaw Team
"""

import threading
import time
import logging
from typing import Optional, Dict, Any, List

import numpy as np

logger = logging.getLogger(__name__)

# 5 个相机方向 → (link_name, sensor_name)
CAMERAS = {
    "front": ("cam_front_link", "cam_front"),
    "rear":  ("cam_rear_link",  "cam_rear"),
    "left":  ("cam_left_link",  "cam_left"),
    "right": ("cam_right_link", "cam_right"),
    "down":  ("cam_down_link",  "cam_down"),
}


class GzSensorBridge:
    """Gazebo 传感器数据桥接器 — 5 相机 + 1 激光雷达"""

    def __init__(self, model_name: str = "x500_lidar_2d_cam_0", world_name: str = "urban_rescue"):
        self.model_name = model_name
        self.world_name = world_name
        self._running = False
        self._node = None

        # 4 相机数据缓冲
        self._cam_locks: Dict[str, threading.Lock] = {}
        self._cam_images: Dict[str, Optional[np.ndarray]] = {}
        self._cam_ts: Dict[str, float] = {}
        self._cam_wh: Dict[str, tuple] = {}
        self._cam_fps: Dict[str, '_FPSCounter'] = {}

        for d in CAMERAS:
            self._cam_locks[d] = threading.Lock()
            self._cam_images[d] = None
            self._cam_ts[d] = 0.0
            self._cam_wh[d] = (0, 0)
            self._cam_fps[d] = _FPSCounter()

        # 激光雷达
        self._lidar_lock = threading.Lock()
        self._lidar_data: Optional[Dict[str, Any]] = None
        self._lidar_ts: float = 0.0
        self._lidar_fps_counter = _FPSCounter()

    # ── Topic 路径 ──

    def _camera_topic(self, direction: str) -> str:
        link, sensor = CAMERAS[direction]
        return (f"/world/{self.world_name}/model/{self.model_name}"
                f"/link/{link}/sensor/{sensor}/image")

    def _lidar_topic(self) -> str:
        return (f"/world/{self.world_name}/model/{self.model_name}"
                f"/link/link/sensor/lidar_2d_v2/scan")

    # ── 启动 / 停止 ──

    def start(self) -> bool:
        """启动传感器订阅"""
        if self._running:
            logger.warning("GzSensorBridge 已在运行")
            return True

        try:
            from gz.transport13 import Node
            from gz.msgs10.image_pb2 import Image
            from gz.msgs10.laserscan_pb2 import LaserScan

            self._node = Node()

            # 订阅 4 个相机
            for direction in CAMERAS:
                topic = self._camera_topic(direction)
                cb = self._make_camera_callback(direction)
                if self._node.subscribe(Image, topic, cb):
                    logger.info(f"订阅相机 [{direction}]: {topic}")
                else:
                    logger.warning(f"相机订阅失败 [{direction}]: {topic}")

            # 订阅激光雷达
            lidar_topic = self._lidar_topic()
            if self._node.subscribe(LaserScan, lidar_topic, self._on_lidar_scan):
                logger.info(f"订阅激光雷达: {lidar_topic}")
            else:
                logger.warning(f"激光雷达订阅失败: {lidar_topic}")

            self._running = True
            logger.info("GzSensorBridge 启动成功 (4 相机 + 1 激光雷达)")
            return True

        except Exception as e:
            logger.error(f"GzSensorBridge 启动失败: {e}")
            return False

    def stop(self):
        self._running = False
        self._node = None
        logger.info("GzSensorBridge 已停止")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── 相机回调（工厂方法，每个方向一个） ──

    def _make_camera_callback(self, direction: str):
        """为指定方向创建相机回调闭包"""
        def _callback(msg):
            try:
                w, h = msg.width, msg.height
                fmt = msg.pixel_format_type
                data = msg.data
                raw = np.frombuffer(data, dtype=np.uint8) if isinstance(data, (bytes, bytearray)) else np.array(data, dtype=np.uint8)

                if fmt == 4 and raw.size == w * h * 3:  # RGB
                    img = raw.reshape((h, w, 3))[:, :, ::-1].copy()
                elif fmt == 1 and raw.size == w * h:  # Grayscale
                    img = raw.reshape((h, w))
                elif raw.size == w * h * 3:
                    img = raw.reshape((h, w, 3))[:, :, ::-1].copy()
                elif raw.size == w * h * 4:  # RGBA
                    img = raw.reshape((h, w, 4))[:, :, :3][:, :, ::-1].copy()
                else:
                    return

                with self._cam_locks[direction]:
                    self._cam_images[direction] = img
                    self._cam_ts[direction] = time.time()
                    self._cam_wh[direction] = (w, h)
                self._cam_fps[direction].tick()

            except Exception as e:
                logger.debug(f"相机 [{direction}] 帧解码错误: {e}")

        return _callback

    # ── 激光雷达回调 ──

    def _on_lidar_scan(self, msg):
        try:
            ranges = list(msg.ranges)
            h_count = msg.count           # 水平采样数
            v_count = msg.vertical_count  # 垂直层数 (2D时为0或1)

            scan_data = {
                "ranges": ranges,
                "angle_min": msg.angle_min,
                "angle_max": msg.angle_max,
                "angle_increment": msg.angle_step,
                "range_min": msg.range_min,
                "range_max": msg.range_max,
                "count": h_count,
                # 3D 扩展字段
                "vertical_count": v_count if v_count > 0 else 1,
                "vertical_angle_min": msg.vertical_angle_min,
                "vertical_angle_max": msg.vertical_angle_max,
                "vertical_angle_step": msg.vertical_angle_step,
                "is_3d": v_count > 1,
                "total_points": len(ranges),
            }
            with self._lidar_lock:
                self._lidar_data = scan_data
                self._lidar_ts = time.time()
            self._lidar_fps_counter.tick()
        except Exception as e:
            logger.debug(f"雷达数据解码错误: {e}")

    # ── 数据获取接口 ──

    def get_camera_image(self, direction: str = "front") -> Optional[np.ndarray]:
        """获取指定方向相机图像 (BGR numpy array)"""
        if direction not in CAMERAS:
            return None
        with self._cam_locks[direction]:
            return self._cam_images[direction].copy() if self._cam_images[direction] is not None else None

    def get_camera_info(self, direction: str = "front") -> Dict[str, Any]:
        """获取指定方向相机信息"""
        if direction not in CAMERAS:
            return {"has_data": False, "width": 0, "height": 0, "timestamp": 0, "fps": 0}
        with self._cam_locks[direction]:
            w, h = self._cam_wh[direction]
            return {
                "has_data": self._cam_images[direction] is not None,
                "width": w,
                "height": h,
                "timestamp": self._cam_ts[direction],
                "fps": self._cam_fps[direction].fps,
            }

    def get_all_cameras(self) -> Dict[str, Optional[np.ndarray]]:
        """获取全部 4 个相机图像"""
        return {d: self.get_camera_image(d) for d in CAMERAS}

    def get_all_camera_info(self) -> Dict[str, Dict]:
        """获取全部 4 个相机信息"""
        return {d: self.get_camera_info(d) for d in CAMERAS}

    def get_lidar_scan(self) -> Optional[Dict[str, Any]]:
        with self._lidar_lock:
            return self._lidar_data.copy() if self._lidar_data is not None else None

    def get_lidar_info(self) -> Dict[str, Any]:
        with self._lidar_lock:
            return {
                "has_data": self._lidar_data is not None,
                "timestamp": self._lidar_ts,
                "fps": self._lidar_fps_counter.fps,
            }

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "model": self.model_name,
            "world": self.world_name,
            "cameras": self.get_all_camera_info(),
            "lidar": self.get_lidar_info(),
        }


class _FPSCounter:
    def __init__(self, window: float = 2.0):
        self._window = window
        self._times: list[float] = []
        self._lock = threading.Lock()

    def tick(self):
        now = time.time()
        with self._lock:
            self._times.append(now)
            cutoff = now - self._window
            self._times = [t for t in self._times if t > cutoff]

    @property
    def fps(self) -> float:
        with self._lock:
            if len(self._times) < 2:
                return 0.0
            span = self._times[-1] - self._times[0]
            return (len(self._times) - 1) / span if span > 0 else 0.0
