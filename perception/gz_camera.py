"""
perception/gz_camera.py
Gazebo 相机桥接 — 从 Gazebo Transport topic 抓取摄像头图像。

支持 x500_lidar_2d_cam 的 4 个方向摄像头 (前/后/左/右)。
抓到的图像可以直接送给 VLM 分析。
"""

import logging
import time
import numpy as np
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# 相机 topic 模板
CAMERA_TOPIC_TEMPLATE = (
    "/world/{world}/model/{model}/link/cam_{direction}_link"
    "/sensor/cam_{direction}/image"
)

DIRECTIONS = ["front", "left", "right", "rear", "down"]

# 中文方向映射
DIR_CN = {"front": "前方", "rear": "后方", "left": "左方", "right": "右方", "down": "下方"}


class GzCamera:
    """
    Gazebo 相机图像抓取器。

    用法:
        cam = GzCamera(world="urban_rescue", model="x500_lidar_2d_cam_0")
        img = cam.capture("front")   # 抓前方摄像头 -> numpy BGR
        cam.capture_all()             # 抓所有方向
    """

    def __init__(
        self,
        world: str = "urban_rescue",
        model: str = "x500_lidar_2d_cam_0",
        timeout_ms: int = 3000,
    ):
        self._world = world
        self._model = model
        self._timeout_ms = timeout_ms
        self._node = None
        self._last_images: Dict[str, np.ndarray] = {}
        self._subscribers = {}

    def _ensure_node(self):
        """延迟初始化 Gazebo Transport node。"""
        if self._node is not None:
            return
        try:
            from gz.transport13 import Node
            self._node = Node()
            logger.info("Gazebo Transport Node 初始化成功")
        except ImportError:
            logger.error("gz.transport13 未安装, 无法抓取相机图像")
            raise

    def _get_topic(self, direction: str) -> str:
        """获取指定方向相机的 topic。"""
        return CAMERA_TOPIC_TEMPLATE.format(
            world=self._world, model=self._model, direction=direction,
        )

    def capture(self, direction: str = "front") -> Optional[np.ndarray]:
        """
        抓取指定方向的相机图像。

        Args:
            direction: "front" / "rear" / "left" / "right"

        Returns:
            np.ndarray (BGR) 或 None (失败时)
        """
        self._ensure_node()

        topic = self._get_topic(direction)

        try:
            from gz.msgs10.image_pb2 import Image as GzImage

            # 用 request 方式获取最新帧
            result = [None]

            def _cb(msg):
                result[0] = msg

            # 订阅方式: subscribe + 等待
            subscribed = self._node.subscribe(GzImage, topic, _cb)
            if not subscribed:
                logger.warning(f"订阅失败: {topic}")
                return None

            # 等待图像到达
            deadline = time.time() + self._timeout_ms / 1000
            while result[0] is None and time.time() < deadline:
                time.sleep(0.05)

            self._node.unsubscribe(topic)

            if result[0] is None:
                logger.warning(f"超时未收到图像: {topic}")
                return None

            # 解析图像
            img = self._decode_gz_image(result[0])
            if img is not None:
                self._last_images[direction] = img
                logger.debug(f"抓取 {DIR_CN.get(direction, direction)} 图像: {img.shape}")
            return img

        except Exception as e:
            logger.error(f"抓取 {direction} 图像失败: {e}")
            return None

    def capture_all(self) -> Dict[str, np.ndarray]:
        """抓取所有方向的图像。"""
        images = {}
        for d in DIRECTIONS:
            img = self.capture(d)
            if img is not None:
                images[d] = img
        return images

    def get_last_image(self, direction: str = "front") -> Optional[np.ndarray]:
        """获取最后一次抓到的图像 (不重新抓取)。"""
        return self._last_images.get(direction)

    def _decode_gz_image(self, gz_msg) -> Optional[np.ndarray]:
        """将 Gazebo Image protobuf 消息解码为 numpy BGR 图像。"""
        try:
            w = gz_msg.width
            h = gz_msg.height
            pixel_format = gz_msg.pixel_format_type

            data = gz_msg.data
            if not data:
                return None

            raw = np.frombuffer(data, dtype=np.uint8)

            # 常见格式处理
            # pixel_format: 1=L_INT8, 2=L_INT16, 3=RGB_INT8, 4=RGBA_INT8,
            #               5=BGRA_INT8, 6=RGB_FLOAT32, 7=R_FLOAT16, 8=R_FLOAT32
            if pixel_format == 3:  # RGB_INT8
                img = raw.reshape(h, w, 3)
                import cv2
                return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif pixel_format == 4:  # RGBA_INT8
                img = raw.reshape(h, w, 4)
                import cv2
                return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif pixel_format == 5:  # BGRA_INT8
                img = raw.reshape(h, w, 4)
                import cv2
                return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            elif pixel_format == 1:  # L_INT8 (灰度)
                img = raw.reshape(h, w)
                import cv2
                return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            else:
                # 尝试按 RGB 处理
                expected = h * w * 3
                if len(raw) >= expected:
                    img = raw[:expected].reshape(h, w, 3)
                    import cv2
                    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                logger.warning(f"未知像素格式: {pixel_format}, 数据长度: {len(raw)}")
                return None

        except Exception as e:
            logger.error(f"图像解码失败: {e}")
            return None


# ── 全局单例 ──────────────────────────────────────────────────────────────────

_camera: Optional[GzCamera] = None


def get_camera() -> Optional[GzCamera]:
    """获取全局相机实例。"""
    return _camera


def init_camera(**kwargs) -> GzCamera:
    """初始化全局相机。"""
    global _camera
    _camera = GzCamera(**kwargs)
    logger.info("Gazebo 相机初始化 (world=%s, model=%s)", kwargs.get("world", "urban_rescue"), kwargs.get("model", "x500_lidar_2d_cam_0"))
    return _camera
