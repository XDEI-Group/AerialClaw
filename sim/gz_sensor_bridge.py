"""
sim.gz_sensor_bridge

Gazebo Harmonic sensor bridge for the AerialClaw Web console.

The Web UI does not read Gazebo Transport topics directly. It receives
``sensor_cameras`` / ``sensor_lidar`` Socket.IO events emitted by ``server.py``.
This bridge is the missing adapter between Gazebo topics and the interface that
``server.py::_start_sensor_stream`` expects:

    - is_running
    - get_camera_image(direction)
    - get_camera_info(direction)
    - get_lidar_scan()
    - get_lidar_info()
    - get_status()

It is intentionally defensive: importing this module does not require Gazebo
Python bindings. ``start()`` returns ``False`` with a clear error when the
bindings or topics are unavailable, instead of crashing the server.
"""

from __future__ import annotations

import logging
import math
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DIRECTIONS = ("front", "rear", "left", "right", "down")


@dataclass
class _CameraSlot:
    topic: str = ""
    image: Optional[np.ndarray] = None
    width: int = 0
    height: int = 0
    frame_count: int = 0
    fps: float = 0.0
    last_ts: float = 0.0
    _fps_window_start: float = field(default_factory=time.time)
    _fps_window_count: int = 0

    def update_fps(self) -> None:
        self.frame_count += 1
        self._fps_window_count += 1
        now = time.time()
        elapsed = now - self._fps_window_start
        if elapsed >= 1.0:
            self.fps = self._fps_window_count / elapsed
            self._fps_window_count = 0
            self._fps_window_start = now
        self.last_ts = now


@dataclass
class _LidarSlot:
    topic: str = ""
    scan: Optional[dict] = None
    frame_count: int = 0
    fps: float = 0.0
    last_ts: float = 0.0
    _fps_window_start: float = field(default_factory=time.time)
    _fps_window_count: int = 0

    def update_fps(self) -> None:
        self.frame_count += 1
        self._fps_window_count += 1
        now = time.time()
        elapsed = now - self._fps_window_start
        if elapsed >= 1.0:
            self.fps = self._fps_window_count / elapsed
            self._fps_window_count = 0
            self._fps_window_start = now
        self.last_ts = now


class GzSensorBridge:
    """Subscribe to Gazebo camera / LiDAR topics and cache latest frames."""

    def __init__(
        self,
        model_name: str = "x500_lidar_2d_cam_0",
        world_name: str = "urban_rescue",
        camera_dirs: Iterable[str] = DIRECTIONS,
        camera_topic_template: str = "/world/{world}/model/{model}/link/cam_{direction}_link/sensor/cam_{direction}/image",
        lidar_topic: Optional[str] = None,
    ):
        self.model_name = model_name
        self.world_name = world_name
        self._camera_dirs = list(camera_dirs)
        self.camera_topic_template = camera_topic_template
        self.lidar_topic = lidar_topic
        self.is_running = False
        self.last_error = ""

        self._node = None
        self._lock = threading.RLock()
        self._cameras: Dict[str, _CameraSlot] = {d: _CameraSlot() for d in self._camera_dirs}
        self._lidar = _LidarSlot()
        self._subscriptions: List[str] = []

        self._ImageMsg = None
        self._LaserScanMsg = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> bool:
        """Create Gazebo Transport subscribers.

        Returns False when Gazebo Python bindings are not installed or when no
        sensor subscription succeeds. This lets server.py log a warning while
        keeping the rest of AerialClaw usable.
        """
        if self.is_running:
            return True

        try:
            self._load_gz_bindings()
            topics = self._list_topics()
            self._subscribe_cameras(topics)
            self._subscribe_lidar(topics)
        except Exception as exc:  # pragma: no cover - exercised on systems without Gazebo
            self.last_error = str(exc)
            logger.warning("Gazebo sensor bridge start failed: %s", exc, exc_info=True)
            self.stop()
            return False

        if not self._subscriptions:
            self.last_error = (
                "No Gazebo camera/LiDAR topics subscribed. Check PX4_GZ_WORLD, "
                "PX4_SIM_MODEL, and `gz topic -l`."
            )
            logger.warning(self.last_error)
            self.stop()
            return False

        self.is_running = True
        logger.info(
            "Gazebo sensor bridge started: world=%s model=%s topics=%s",
            self.world_name,
            self.model_name,
            self._subscriptions,
        )
        return True

    def stop(self) -> None:
        if self._node is not None:
            for topic in list(self._subscriptions):
                try:
                    self._node.unsubscribe(topic)
                except Exception:
                    logger.debug("Failed to unsubscribe %s", topic, exc_info=True)
        self._subscriptions.clear()
        self.is_running = False

    # ------------------------------------------------------------------
    # Public API consumed by server.py / skills
    # ------------------------------------------------------------------
    def get_camera_image(self, direction: str = "front") -> Optional[np.ndarray]:
        direction = self._normalize_direction(direction)
        with self._lock:
            slot = self._cameras.get(direction)
            return None if slot is None or slot.image is None else slot.image.copy()

    def get_camera_info(self, direction: str = "front") -> dict:
        direction = self._normalize_direction(direction)
        with self._lock:
            slot = self._cameras.get(direction, _CameraSlot())
            return {
                "direction": direction,
                "topic": slot.topic,
                "width": slot.width,
                "height": slot.height,
                "fps": slot.fps,
                "frame_count": slot.frame_count,
                "last_ts": slot.last_ts,
            }

    def get_lidar_scan(self) -> Optional[dict]:
        with self._lock:
            if self._lidar.scan is None:
                return None
            scan = dict(self._lidar.scan)
            if "ranges" in scan:
                scan["ranges"] = list(scan["ranges"])
            return scan

    def get_lidar_info(self) -> dict:
        with self._lock:
            return {
                "topic": self._lidar.topic,
                "fps": self._lidar.fps,
                "frame_count": self._lidar.frame_count,
                "last_ts": self._lidar.last_ts,
            }

    def get_status(self) -> dict:
        with self._lock:
            return {
                "running": self.is_running,
                "world": self.world_name,
                "model": self.model_name,
                "last_error": self.last_error,
                "subscriptions": list(self._subscriptions),
                "cameras": {d: self.get_camera_info(d) for d in self._camera_dirs},
                "lidar": self.get_lidar_info(),
            }

    # ------------------------------------------------------------------
    # Gazebo subscriptions
    # ------------------------------------------------------------------
    def _load_gz_bindings(self) -> None:
        try:
            from gz.transport13 import Node
        except ImportError as exc:
            raise RuntimeError(
                "Gazebo Python binding `gz.transport13` is not installed. "
                "Install Gazebo Harmonic Python bindings and ensure they are on PYTHONPATH."
            ) from exc

        self._node = Node()

        try:
            from gz.msgs10.image_pb2 import Image
            self._ImageMsg = Image
        except ImportError as exc:
            raise RuntimeError("Gazebo image protobuf `gz.msgs10.image_pb2.Image` is unavailable") from exc

        # Harmonic laser scan bindings are usually here. Keep optional because
        # camera streaming should still work even if the lidar message package
        # name differs on a distro.
        for mod_name, cls_name in (
            ("gz.msgs10.laser_scan_pb2", "LaserScan"),
            ("gz.msgs10.laserscan_pb2", "LaserScan"),
        ):
            try:
                mod = __import__(mod_name, fromlist=[cls_name])
                self._LaserScanMsg = getattr(mod, cls_name)
                break
            except Exception:
                continue

    def _list_topics(self) -> List[str]:
        # gz.transport Node APIs vary slightly by version. The explicit default
        # topics below are enough for AerialClaw's bundled model; listing topics
        # lets us auto-correct names if PX4/Gazebo adds a suffix.
        topics: List[str] = []
        for attr in ("topic_list", "topics"):
            fn = getattr(self._node, attr, None)
            if callable(fn):
                try:
                    raw = fn()
                    topics = [str(x) for x in raw]
                    break
                except Exception:
                    logger.debug("Gazebo Node.%s() failed", attr, exc_info=True)

        if topics:
            return topics

        # CLI fallback works on Gazebo Harmonic even when Python transport does
        # not expose a stable topic-list helper.
        try:
            import subprocess

            result = subprocess.run(
                ["gz", "topic", "-l"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode == 0:
                topics = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            logger.debug("`gz topic -l` fallback failed", exc_info=True)
        return topics

    def _subscribe_cameras(self, topics: List[str]) -> None:
        for direction in self._camera_dirs:
            expected = self.camera_topic_template.format(
                world=self.world_name,
                model=self.model_name,
                direction=direction,
            )
            topic = self._choose_topic(topics, expected, [f"cam_{direction}", "/image"])
            if not topic:
                continue

            def _cb(msg, direction=direction):
                self._on_image(direction, msg)

            ok = self._node.subscribe(self._ImageMsg, topic, _cb)
            if ok:
                with self._lock:
                    self._cameras[direction].topic = topic
                    self._subscriptions.append(topic)
            else:
                logger.warning("Failed to subscribe camera topic: %s", topic)

    def _subscribe_lidar(self, topics: List[str]) -> None:
        if self._LaserScanMsg is None:
            self.last_error = "Gazebo LaserScan protobuf is unavailable; LiDAR disabled"
            logger.warning(self.last_error)
            return

        candidates = []
        if self.lidar_topic:
            candidates.append(self.lidar_topic)
        candidates.extend(self._find_lidar_topics(topics))
        candidates.extend([
            f"/world/{self.world_name}/model/{self.model_name}/link/link/sensor/lidar_2d_v2/scan",
            f"/world/{self.world_name}/model/{self.model_name}/link/lidar_2d_v2/link/sensor/lidar_2d_v2/scan",
        ])

        seen = set()
        for topic in candidates:
            if not topic or topic in seen:
                continue
            seen.add(topic)

            ok = self._node.subscribe(self._LaserScanMsg, topic, self._on_lidar)
            if ok:
                with self._lock:
                    self._lidar.topic = topic
                    self._subscriptions.append(topic)
                return
        logger.warning("No LiDAR topic subscribed. Available lidar-like topics: %s", self._find_lidar_topics(topics))

    @staticmethod
    def _choose_topic(topics: List[str], expected: str, required_parts: List[str]) -> str:
        if expected in topics or not topics:
            return expected
        lowered_parts = [p.lower() for p in required_parts]
        for topic in topics:
            low = topic.lower()
            if all(p in low for p in lowered_parts):
                return topic
        return expected

    @staticmethod
    def _find_lidar_topics(topics: List[str]) -> List[str]:
        result = []
        for topic in topics:
            low = topic.lower()
            if ("lidar" in low or "laser" in low or "gpu_lidar" in low) and (
                low.endswith("/scan") or "scan" in low or "points" in low
            ):
                result.append(topic)
        return result

    # ------------------------------------------------------------------
    # Message decoding
    # ------------------------------------------------------------------
    def _on_image(self, direction: str, msg) -> None:
        img = self._decode_image(msg)
        if img is None:
            return
        with self._lock:
            slot = self._cameras[direction]
            slot.image = img
            slot.height, slot.width = img.shape[:2]
            slot.update_fps()

    def _decode_image(self, msg) -> Optional[np.ndarray]:
        try:
            width = int(getattr(msg, "width"))
            height = int(getattr(msg, "height"))
            data = getattr(msg, "data", b"")
            if width <= 0 or height <= 0 or not data:
                return None
            raw = np.frombuffer(data, dtype=np.uint8)
            pixel_format = int(getattr(msg, "pixel_format_type", 0))
            pixel_format_name = str(getattr(msg, "pixel_format", "") or getattr(msg, "format", "")).upper()

            # Gazebo enum values commonly used by gz.msgs.PixelFormatType:
            # RGB_INT8=3, RGBA_INT8=4, BGRA_INT8=5, L_INT8=1.
            if pixel_format == 3 or "RGB" in pixel_format_name and "RGBA" not in pixel_format_name:
                arr = raw[: width * height * 3].reshape(height, width, 3)
                return arr[:, :, ::-1].copy()  # RGB -> BGR for cv2.imencode in server.py
            if pixel_format == 4 or "RGBA" in pixel_format_name:
                arr = raw[: width * height * 4].reshape(height, width, 4)
                return arr[:, :, :3][:, :, ::-1].copy()
            if pixel_format == 5 or "BGRA" in pixel_format_name:
                arr = raw[: width * height * 4].reshape(height, width, 4)
                return arr[:, :, :3].copy()
            if pixel_format == 1 or "L_INT8" in pixel_format_name:
                gray = raw[: width * height].reshape(height, width)
                return np.repeat(gray[:, :, None], 3, axis=2)

            # Fallback: infer from payload size.
            if raw.size >= width * height * 3:
                arr = raw[: width * height * 3].reshape(height, width, 3)
                return arr[:, :, ::-1].copy()
            if raw.size >= width * height:
                gray = raw[: width * height].reshape(height, width)
                return np.repeat(gray[:, :, None], 3, axis=2)
        except Exception:
            logger.debug("Failed to decode Gazebo image", exc_info=True)
        return None

    def _on_lidar(self, msg) -> None:
        scan = self._decode_lidar(msg)
        if scan is None:
            return
        with self._lock:
            self._lidar.scan = scan
            self._lidar.update_fps()

    def _decode_lidar(self, msg) -> Optional[dict]:
        try:
            ranges = list(getattr(msg, "ranges", []) or getattr(msg, "range", []))
            if not ranges:
                return None

            angle_min = float(getattr(msg, "angle_min", -math.pi))
            angle_max = float(getattr(msg, "angle_max", math.pi))
            angle_step = float(
                getattr(msg, "angle_step", 0.0)
                or getattr(msg, "angle_increment", 0.0)
                or ((angle_max - angle_min) / max(1, len(ranges) - 1))
            )
            range_min = float(getattr(msg, "range_min", 0.1))
            range_max = float(getattr(msg, "range_max", 30.0))

            vertical_count = int(getattr(msg, "vertical_count", 1) or 1)
            count = int(getattr(msg, "count", len(ranges) // max(1, vertical_count)) or len(ranges))

            return {
                "ranges": [float(r) if _is_number(r) else math.inf for r in ranges],
                "angle_min": angle_min,
                "angle_max": angle_max,
                "angle_increment": angle_step,
                "range_min": range_min,
                "range_max": range_max,
                "count": count,
                "vertical_count": vertical_count,
                "vertical_angle_min": float(getattr(msg, "vertical_angle_min", 0.0) or 0.0),
                "vertical_angle_max": float(getattr(msg, "vertical_angle_max", 0.0) or 0.0),
                "is_3d": vertical_count > 1,
                "total_points": len(ranges),
            }
        except Exception:
            logger.debug("Failed to decode Gazebo LiDAR scan", exc_info=True)
            return None

    @staticmethod
    def _normalize_direction(direction: str) -> str:
        aliases = {
            "forward": "front",
            "back": "rear",
            "backward": "rear",
            "bottom": "down",
        }
        direction = aliases.get((direction or "front").lower(), (direction or "front").lower())
        return direction if direction in DIRECTIONS else "front"


def _is_number(value) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False
