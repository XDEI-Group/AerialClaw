"""
airsim_adapter.py
AirSim SimpleFlight 仿真适配器。

连接方式: airsim Python API，直接连接 AirSim 服务器（默认端口 41451）。
支持本地和远程连接。

适用场景:
    - AirSim SimpleFlight 模式（不需要 PX4/MAVLink）
    - 远程 AirSim 服务器（如 GPU 服务器上的 UE4 环境）
    - OpenFly-Platform 等第三方 AirSim 环境

依赖:
    pip install airsim
"""

import math
import time
import logging
from typing import Optional

import numpy as np

try:
    import airsim
except ImportError:
    airsim = None

from adapters.sim_adapter import (
    SimAdapter, Position, GPSPosition, VehicleState, ActionResult,
)

logger = logging.getLogger(__name__)


def _quaternion_to_euler(q) -> tuple:
    """四元数转欧拉角 (roll, pitch, yaw) 弧度。"""
    w, x, y, z = q.w_val, q.x_val, q.y_val, q.z_val
    # Roll
    sinr = 2.0 * (w * x + y * z)
    cosr = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr, cosr)
    # Pitch
    sinp = 2.0 * (w * y - z * x)
    sinp = max(-1.0, min(1.0, sinp))
    pitch = math.asin(sinp)
    # Yaw
    siny = 2.0 * (w * z + x * y)
    cosy = 1.0 - 2.0 * (y * y + z * z)
    yaw = math.atan2(siny, cosy)
    return roll, pitch, yaw


class AirSimAdapter(SimAdapter):
    """AirSim SimpleFlight 适配器，通过 airsim Python API 控制。"""

    name = "airsim_simpleflight"
    description = "AirSim SimpleFlight via airsim Python API (local or remote)"
    supported_vehicles = ["multirotor"]

    def __init__(self, vehicle_name: str = ""):
        """
        Args:
            vehicle_name: AirSim 中的无人机名称，空字符串表示默认无人机。
        """
        if airsim is None:
            raise ImportError("airsim 包未安装，请执行: pip install airsim")
        self._client: Optional[airsim.MultirotorClient] = None
        self._connected = False
        self._vehicle_name = vehicle_name
        self._home_position: Optional[Position] = None

    # ── 连接管理 ──────────────────────────────────────────────────────────────

    def connect(self, connection_str: str = "", timeout: float = 15.0) -> bool:
        """
        连接 AirSim 服务器。

        Args:
            connection_str: "ip:port" 格式，默认 "127.0.0.1:41451"
            timeout: 连接超时（秒）
        """
        ip = "127.0.0.1"
        port = 41451

        if connection_str:
            parts = connection_str.split(":")
            ip = parts[0]
            if len(parts) > 1:
                port = int(parts[1])

        logger.info(f"连接 AirSim: {ip}:{port} (vehicle={self._vehicle_name or 'default'})")

        try:
            self._client = airsim.MultirotorClient(ip=ip, port=port, timeout_value=int(timeout))
            self._client.confirmConnection()
            self._client.enableApiControl(True, vehicle_name=self._vehicle_name)
            self._client.armDisarm(True, vehicle_name=self._vehicle_name)
            self._connected = True

            # 记录起飞点
            state = self._client.getMultirotorState(vehicle_name=self._vehicle_name)
            pos = state.kinematics_estimated.position
            self._home_position = Position(north=pos.x_val, east=pos.y_val, down=pos.z_val)

            logger.info(f"✅ AirSim 连接成功: {ip}:{port}")
            return True

        except Exception as e:
            logger.error(f"❌ AirSim 连接失败: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        if self._client and self._connected:
            try:
                self._client.armDisarm(False, vehicle_name=self._vehicle_name)
                self._client.enableApiControl(False, vehicle_name=self._vehicle_name)
            except Exception:
                pass
        self._connected = False
        self._client = None
        logger.info("AirSim 已断开")

    def is_connected(self) -> bool:
        if not self._connected or not self._client:
            return False
        try:
            self._client.getMultirotorState(vehicle_name=self._vehicle_name)
            return True
        except Exception:
            self._connected = False
            return False

    # ── 状态查询 ──────────────────────────────────────────────────────────────

    def _get_raw_state(self):
        """获取 AirSim 原始状态。"""
        return self._client.getMultirotorState(vehicle_name=self._vehicle_name)

    def get_state(self) -> VehicleState:
        if not self._connected:
            return VehicleState()

        try:
            state = self._get_raw_state()
            pos = state.kinematics_estimated.position
            vel = state.kinematics_estimated.linear_velocity
            orient = state.kinematics_estimated.orientation
            _, _, yaw = _quaternion_to_euler(orient)

            # AirSim landed_state: 0=Landed, 1=Flying
            in_air = state.landed_state != airsim.LandedState.Landed

            # GPS: AirSim 提供 gps_location
            gps = state.gps_location if hasattr(state, 'gps_location') else None
            gps_pos = None
            if gps:
                gps_pos = GPSPosition(
                    lat=gps.latitude, lon=gps.longitude, alt=gps.altitude
                )

            return VehicleState(
                armed=True,  # SimpleFlight 模式下 enableApiControl 后即为 armed
                in_air=in_air,
                mode="SimpleFlight",
                position_ned=Position(north=pos.x_val, east=pos.y_val, down=pos.z_val),
                position_gps=gps_pos,
                battery_voltage=12.6,  # SimpleFlight 不提供真实电池数据
                battery_percent=1.0,
                heading_deg=math.degrees(yaw) % 360,
                velocity=[vel.x_val, vel.y_val, vel.z_val],
            )
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return VehicleState()

    def get_position(self) -> Position:
        if not self._connected:
            return Position()
        try:
            state = self._get_raw_state()
            pos = state.kinematics_estimated.position
            return Position(north=pos.x_val, east=pos.y_val, down=pos.z_val)
        except Exception as e:
            logger.error(f"获取位置失败: {e}")
            return Position()

    def get_gps(self) -> GPSPosition:
        if not self._connected:
            return GPSPosition()
        try:
            state = self._get_raw_state()
            gps = state.gps_location if hasattr(state, 'gps_location') else None
            if gps:
                return GPSPosition(lat=gps.latitude, lon=gps.longitude, alt=gps.altitude)
            # 没有 GPS 数据时用 NED 位置模拟
            pos = state.kinematics_estimated.position
            return GPSPosition(lat=0.0, lon=0.0, alt=-pos.z_val)
        except Exception:
            return GPSPosition()

    def get_battery(self) -> tuple:
        # SimpleFlight 不提供真实电池数据，返回模拟值
        return (12.6, 1.0)

    def is_armed(self) -> bool:
        return self._connected  # SimpleFlight: API 控制开启即为 armed

    def is_in_air(self) -> bool:
        if not self._connected:
            return False
        try:
            state = self._get_raw_state()
            return state.landed_state != airsim.LandedState.Landed
        except Exception:
            return False

    # ── 基本飞行操作 ──────────────────────────────────────────────────────────

    def arm(self) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")
        try:
            self._client.enableApiControl(True, vehicle_name=self._vehicle_name)
            self._client.armDisarm(True, vehicle_name=self._vehicle_name)
            return ActionResult(success=True, message="Armed")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def disarm(self) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")
        try:
            self._client.armDisarm(False, vehicle_name=self._vehicle_name)
            return ActionResult(success=True, message="Disarmed")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def takeoff(self, altitude: float = 5.0) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")

        start = time.time()
        try:
            self._client.enableApiControl(True, vehicle_name=self._vehicle_name)
            self._client.armDisarm(True, vehicle_name=self._vehicle_name)

            # AirSim takeoff 飞到默认高度（约 -3m），然后我们调整到目标高度
            self._client.takeoffAsync(vehicle_name=self._vehicle_name).join()

            # 飞到目标高度
            pos = self.get_position()
            target_z = -abs(altitude)  # NED: 负值 = 向上
            if abs(pos.down - target_z) > 0.5:
                self._client.moveToZAsync(
                    target_z, 2.0, vehicle_name=self._vehicle_name
                ).join()

            elapsed = round(time.time() - start, 2)
            final_pos = self.get_position()

            return ActionResult(
                success=True,
                message=f"起飞到 {abs(final_pos.down):.1f}m",
                data={"altitude": abs(final_pos.down), "position": final_pos.to_list()},
                duration=elapsed,
            )
        except Exception as e:
            return ActionResult(
                success=False, message=f"起飞失败: {e}",
                duration=round(time.time() - start, 2),
            )

    def land(self) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")

        start = time.time()
        try:
            self._client.landAsync(vehicle_name=self._vehicle_name).join()
            elapsed = round(time.time() - start, 2)
            return ActionResult(
                success=True, message="已降落",
                data={"position": self.get_position().to_list()},
                duration=elapsed,
            )
        except Exception as e:
            return ActionResult(
                success=False, message=f"降落失败: {e}",
                duration=round(time.time() - start, 2),
            )

    def fly_to_ned(self, north: float, east: float, down: float, speed: float = 2.0) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")

        start = time.time()
        try:
            # AirSim moveToPositionAsync: x=north, y=east, z=down (NED)
            self._client.moveToPositionAsync(
                north, east, down, speed,
                vehicle_name=self._vehicle_name,
            ).join()

            elapsed = round(time.time() - start, 2)
            final_pos = self.get_position()

            return ActionResult(
                success=True,
                message=f"到达 NED({north:.1f},{east:.1f},{down:.1f})",
                data={"position": final_pos.to_list()},
                duration=elapsed,
            )
        except Exception as e:
            return ActionResult(
                success=False, message=f"飞行失败: {e}",
                duration=round(time.time() - start, 2),
            )

    def hover(self, duration: float = 5.0) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")

        start = time.time()
        try:
            self._client.hoverAsync(vehicle_name=self._vehicle_name).join()
            time.sleep(duration)
            elapsed = round(time.time() - start, 2)
            return ActionResult(
                success=True, message=f"悬停 {duration}s",
                data={"position": self.get_position().to_list()},
                duration=elapsed,
            )
        except Exception as e:
            return ActionResult(
                success=False, message=f"悬停失败: {e}",
                duration=round(time.time() - start, 2),
            )

    def return_to_launch(self) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")

        if not self._home_position:
            return ActionResult(success=False, message="无起飞点记录")

        start = time.time()
        try:
            # 先飞回起飞点上方
            home = self._home_position
            self._client.moveToPositionAsync(
                home.north, home.east, -5.0, 3.0,
                vehicle_name=self._vehicle_name,
            ).join()
            # 降落
            self._client.landAsync(vehicle_name=self._vehicle_name).join()

            elapsed = round(time.time() - start, 2)
            return ActionResult(
                success=True, message="已返航降落",
                data={"position": self.get_position().to_list()},
                duration=elapsed,
            )
        except Exception as e:
            return ActionResult(
                success=False, message=f"返航失败: {e}",
                duration=round(time.time() - start, 2),
            )

    # ── 扩展接口 ──────────────────────────────────────────────────────────────

    def set_heading(self, heading_deg: float) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")
        try:
            yaw_rad = math.radians(heading_deg)
            pos = self.get_position()
            self._client.moveToPositionAsync(
                pos.north, pos.east, pos.down, 1.0,
                yaw_mode=airsim.YawMode(is_rate=False, yaw_or_rate=heading_deg),
                vehicle_name=self._vehicle_name,
            ).join()
            return ActionResult(success=True, message=f"航向 {heading_deg:.0f}°")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def set_velocity_body(self, vx: float, vy: float, vz: float, yaw_rate: float = 0.0) -> ActionResult:
        """
        Body frame 速度控制。
        vx=前, vy=右, vz=下, yaw_rate=偏航角速度(°/s)
        """
        if not self._connected:
            return ActionResult(success=False, message="未连接 AirSim")
        try:
            self._client.moveByVelocityBodyFrameAsync(
                vx, vy, vz, 0.5,
                yaw_mode=airsim.YawMode(is_rate=True, yaw_or_rate=yaw_rate),
                vehicle_name=self._vehicle_name,
            )
            return ActionResult(success=True, message="velocity_body set")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    # ── 感知接口 ──────────────────────────────────────────────────────────────

    def get_camera_image(
        self,
        camera_name: str = "0",
        image_type: int = 0,
    ) -> Optional[np.ndarray]:
        """
        获取相机图像。

        Args:
            camera_name: 相机名称（"0", "front_custom" 等）
            image_type: 0=Scene, 1=DepthPlanar, 5=Segmentation

        Returns:
            np.ndarray: BGR 图像或深度图
        """
        if not self._connected:
            return None
        try:
            img_type = airsim.ImageType(image_type)
            is_float = image_type in (1, 2)  # 深度图用 float
            responses = self._client.simGetImages(
                [airsim.ImageRequest(camera_name, img_type, is_float, False)],
                vehicle_name=self._vehicle_name,
            )
            if not responses or responses[0].height == 0:
                return None

            resp = responses[0]
            if resp.pixels_as_float:
                img = np.array(resp.image_data_float, dtype=np.float32)
                img = img.reshape(resp.height, resp.width)
            else:
                img = np.frombuffer(resp.image_data_uint8, dtype=np.uint8)
                img = img.reshape(resp.height, resp.width, 3)
            return img
        except Exception as e:
            logger.error(f"获取图像失败: {e}")
            return None

    def get_lidar_data(
        self,
        lidar_name: str = "LidarSensor1",
    ) -> Optional[np.ndarray]:
        """
        获取 LiDAR 点云数据。

        Returns:
            np.ndarray: (N, 3) 点云数组
        """
        if not self._connected:
            return None
        try:
            data = self._client.getLidarData(
                lidar_name=lidar_name,
                vehicle_name=self._vehicle_name,
            )
            if len(data.point_cloud) < 3:
                return None
            points = np.array(data.point_cloud, dtype=np.float32).reshape(-1, 3)
            return points
        except Exception as e:
            logger.error(f"获取 LiDAR 数据失败: {e}")
            return None
