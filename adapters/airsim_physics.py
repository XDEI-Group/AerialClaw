"""
airsim_physics.py
物理引擎驱动的 AirSim 适配器（Phase 2）

与 airsim_adapter.py（teleport 版）的关键区别：
  - 用 moveByRollPitchYawZ 实现定向飞行（moveToPosition 在 OpenFly 定制版不可用）
  - 物理引擎驱动飞行，有碰撞检测、真实飞行动力学
  - 无需 hold 线程对抗物理引擎
  - 支持 request_stop() 外部打断正在进行的飞行

坐标系（AirSim NED）：
  x=North, y=East, z=Down（负数=向上）
  spawn 点约 (15, -5, ~2.0)
  上层归零坐标: rel_n = x - spawn_x, rel_e = y - spawn_y
"""

import logging
import math
import time
from typing import Optional

from adapters.sim_adapter import (
    SimAdapter, Position, GPSPosition, VehicleState, ActionResult,
)

logger = logging.getLogger(__name__)

_AIR_THRESHOLD = 1.5   # 离地超过 1.5m 才算在空中
_SAFE_ALT = 50.0       # 安全飞行最低高度（米）


class AirSimPhysicsAdapter(SimAdapter):
    """物理引擎驱动的 AirSim 适配器，使用 moveByRollPitchYawZ API。"""

    name = "airsim_physics"
    description = "AirSim Physics - moveByRollPitchYawZ/takeoff/land API"
    supported_vehicles = ["multirotor"]

    def __init__(self, vehicle_name: str = "drone_1"):
        self._vehicle_name = vehicle_name
        self._client = None          # 状态查询 + 紧急停止
        self._fly_client = None      # 飞行指令
        self._connected = False

        # spawn 点（连接时记录，用于坐标归零）
        self._spawn_x: float = 15.0
        self._spawn_y: float = -5.0
        self._spawn_z: float = 2.0   # AirSim 地面 z（正数，z 减小=向上）

        # 运行时状态
        self.is_flying: bool = False           # 正在飞行中（外部可读）
        self._stop_requested: bool = False     # 外部打断标志
        self._landed: bool = False             # 已着陆标记
        self._last_obstacle_info: dict = {}    # 最近一次避障信息

    # ── 内部工具 ─────────────────────────────────────────────────────────────

    def _get_raw_state(self) -> dict:
        try:
            return self._client.get_multirotor_state(self._vehicle_name) or {}
        except Exception as e:
            logger.warning(f"get_multirotor_state error: {e}")
            return {}

    def _get_xyz(self) -> tuple:
        """读取 AirSim 绝对坐标 (x, y, z)。"""
        raw = self._get_raw_state()
        pos = raw.get("kinematics_estimated", {}).get("position", {})
        return (
            float(pos.get("x_val", self._spawn_x)),
            float(pos.get("y_val", self._spawn_y)),
            float(pos.get("z_val", self._spawn_z)),
        )

    def _get_altitude(self) -> float:
        """当前高度（米，正数=离地高度）。"""
        _, _, z = self._get_xyz()
        return self._spawn_z - z  # spawn_z - z: z 减小 = 向上 = 高度增加

    def _check_collision(self) -> bool:
        """检查是否发生新碰撞（排除起飞时地面接触等旧碰撞记录）。"""
        try:
            col = self._client.sim_get_collision_info(self._vehicle_name)
            if not col.get("has_collided", False):
                return False
            # 只有碰撞时间戳比飞行开始时间更新才算
            col_ts = col.get("time_stamp", 0)
            return col_ts > getattr(self, '_fly_start_ts', 0)
        except Exception:
            return False

    def _check_depth(self, camera_name: str = 'cam_front') -> Optional[float]:
        """用深度摄像头检查障碍距离（米）。失败返回 None。"""
        try:
            resp = self._client.sim_get_images([{
                'camera_name': camera_name,
                'image_type': 2,       # DepthPerspective
                'pixels_as_float': True,
                'compress': False,
            }], vehicle_name=self._vehicle_name)
            if not resp:
                return None
            r = resp[0]
            h, w = r.get('height', 0), r.get('width', 0)
            data = r.get('image_data_float') or []
            if not data or h == 0 or w == 0:
                return None

            import struct as _struct
            if isinstance(data, bytes):
                data = list(_struct.unpack(f'{len(data)//4}f', data))

            # 取中心 1/3 区域最小深度
            h3, w3 = h // 3, w // 3
            min_depth = 999.0
            for row in range(h3, h3 * 2):
                row_start = row * w + w3
                row_end = row_start + w3
                if row_end <= len(data):
                    for d in data[row_start:row_end]:
                        if 0.1 < d < min_depth:
                            min_depth = d
            return min_depth if min_depth < 999.0 else None
        except Exception:
            return None

    def _emergency_hover(self):
        """紧急悬停（使用 _client）。"""
        try:
            self._client.hover_async_join(self._vehicle_name)
        except Exception as e:
            logger.warning(f"Emergency hover failed: {e}")

    def _get_current_yaw(self) -> float:
        """从四元数获取当前 yaw（弧度）。"""
        raw = self._get_raw_state()
        orient = raw.get("kinematics_estimated", {}).get("orientation", {})
        qw = float(orient.get("w_val", 1.0))
        qx = float(orient.get("x_val", 0.0))
        qy = float(orient.get("y_val", 0.0))
        qz = float(orient.get("z_val", 0.0))
        return math.atan2(2.0 * (qw * qz + qx * qy),
                          1.0 - 2.0 * (qy * qy + qz * qz))

    def _fly_to_with_rpyz(self, target_x: float, target_y: float, target_z: float,
                           speed: float = 5.0, timeout_sec: float = 120.0,
                           check_obstacle: bool = False) -> str:
        """
        用 moveByRollPitchYawZ 飞向目标点，主循环控制 pitch/yaw。
        返回: 'ok' / 'stopped' / 'collision' / 'obstacle' / 'timeout'
        """
        MAX_PITCH = 0.35      # 最大前倾角（弧度，约 20°，实测 0.15→~2m/s 太慢）
        SLOW_DIST = 15.0      # 开始减速的距离（米）
        ARRIVE_DIST = 3.0     # 到达判定距离（米）
        CMD_DURATION = 0.5    # 每次指令持续时间（秒）
        CHECK_INTERVAL = 0.1  # 状态检查间隔（秒）
        SAFE_DIST = 8.0       # 障碍物安全距离（米）

        self.is_flying = True
        start_time = time.time()
        check_counter = 0
        # 记录飞行开始时的碰撞时间戳，过滤旧碰撞（如起飞地面接触）
        try:
            col_info = self._client.sim_get_collision_info(self._vehicle_name)
            self._fly_start_ts = col_info.get("time_stamp", 0)
        except Exception:
            self._fly_start_ts = 0

        try:
            while True:
                # 超时检查
                if time.time() - start_time > timeout_sec:
                    logger.warning("_fly_to_with_rpyz: timeout")
                    self._emergency_hover()
                    return 'timeout'

                # 外部打断
                if self._stop_requested:
                    self._stop_requested = False
                    logger.warning("🛑 外部打断！悬停中...")
                    self._emergency_hover()
                    return 'stopped'

                # 读取当前位置
                cx, cy, cz = self._get_xyz()

                # 水平距离和到达判定
                dx = target_x - cx
                dy = target_y - cy
                horiz_dist = math.sqrt(dx * dx + dy * dy)

                if horiz_dist < ARRIVE_DIST:
                    total_dist = math.sqrt(dx*dx + dy*dy + (target_z - cz)**2)
                    logger.info(f"_fly_to_with_rpyz: arrived (dist={total_dist:.2f}m)")
                    self._emergency_hover()
                    return 'ok'

                # 计算 yaw（朝目标方向，NED: atan2(East, North)）
                yaw = math.atan2(dy, dx)

                # 计算 pitch（前倾角，距离越近越小）
                if horiz_dist > SLOW_DIST:
                    pitch = -MAX_PITCH
                else:
                    pitch = -MAX_PITCH * (horiz_dist / SLOW_DIST)

                logger.debug(
                    f"fly rpyz: horiz={horiz_dist:.1f}m yaw={math.degrees(yaw):.1f}° "
                    f"pitch={math.degrees(pitch):.1f}° z={target_z:.2f}"
                )

                # 发送飞行指令
                try:
                    self._fly_client.move_by_roll_pitch_yaw_z(
                        0.0, pitch, yaw, target_z, CMD_DURATION, self._vehicle_name
                    )
                except Exception as e:
                    logger.warning(f"moveByRollPitchYawZ error: {e}")

                # 轮询等待，检查碰撞和障碍
                steps = int(CMD_DURATION / CHECK_INTERVAL)
                for _ in range(steps):
                    time.sleep(CHECK_INTERVAL)
                    check_counter += 1

                    if self._stop_requested:
                        break

                    # 碰撞检测（每 5 次轮询 ≈ 0.5s）
                    if check_counter % 5 == 0:
                        if self._check_collision():
                            logger.warning("💥 检测到碰撞！紧急悬停")
                            self._emergency_hover()
                            return 'collision'

                    # 深度图避障（每 15 次轮询 ≈ 1.5s）
                    if check_obstacle and check_counter % 15 == 0:
                        front_dist = self._check_depth('cam_front')
                        if front_dist is not None and front_dist < SAFE_DIST:
                            logger.warning(f"⚠️ 前方障碍物 {front_dist:.1f}m！自动悬停")
                            self._last_obstacle_info = {
                                'front_dist': front_dist,
                                'direction': '前方',
                            }
                            self._emergency_hover()
                            return 'obstacle'
        finally:
            self.is_flying = False

    def _fly_with_interrupt(self, x: float, y: float, z: float, speed: float,
                             timeout_sec: float = 120.0,
                             check_obstacle: bool = False) -> str:
        """飞向目标点，支持外部打断、碰撞检测、深度避障。"""
        return self._fly_to_with_rpyz(x, y, z, speed, timeout_sec, check_obstacle)

    # ── 连接管理 ──────────────────────────────────────────────────────────────

    def connect(self, connection_str: str = "", timeout: float = 15.0) -> bool:
        ip, port = "127.0.0.1", 41451
        if connection_str:
            parts = connection_str.split(":")
            ip = parts[0]
            if len(parts) > 1:
                try:
                    port = int(parts[1])
                except ValueError:
                    pass
        try:
            from adapters.airsim_rpc import AirSimDirectClient

            # 主客户端（状态查询 + 紧急停止）
            self._client = AirSimDirectClient(ip, port, timeout=timeout)
            if not self._client.connect():
                raise ConnectionError(f"Cannot connect to AirSim at {ip}:{port}")
            if not self._client.ping():
                raise ConnectionError("AirSim ping failed")

            # 飞行指令专用客户端（避免和状态查询抢 socket 锁）
            self._fly_client = AirSimDirectClient(ip, port, timeout=max(timeout, 30.0))
            if not self._fly_client.connect():
                logger.warning("Fly client connect failed, sharing main client")
                self._fly_client = self._client

            # 启用 API 控制 + 解锁
            self._client.enable_api_control(True, self._vehicle_name)
            self._client.arm_disarm(True, self._vehicle_name)
            self._connected = True

            # 等待物理引擎稳定，记录 spawn 坐标
            logger.info("Waiting for physics engine to stabilize...")
            time.sleep(1.5)
            x, y, z = self._get_xyz()
            self._spawn_x = x
            self._spawn_y = y
            self._spawn_z = z
            logger.info(
                f"AirSimPhysics connected: {ip}:{port}, "
                f"spawn=({self._spawn_x:.2f}, {self._spawn_y:.2f}, {self._spawn_z:.3f})"
            )
            return True

        except Exception as e:
            logger.error(f"AirSimPhysics connect failed: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        # 如果正在飞行，先悬停
        if self.is_flying:
            self._stop_requested = True
            time.sleep(0.5)

        if self._client:
            try:
                self._client.enable_api_control(False, self._vehicle_name)
            except Exception:
                pass
            try:
                self._client.close()
            except Exception:
                pass

        if self._fly_client and self._fly_client is not self._client:
            try:
                self._fly_client.close()
            except Exception:
                pass

        self._connected = False
        self._client = None
        self._fly_client = None

    def is_connected(self) -> bool:
        return self._connected

    # ── 状态查询 ──────────────────────────────────────────────────────────────

    def get_state(self) -> Optional[VehicleState]:
        if not self._connected:
            return None
        try:
            x, y, z = self._get_xyz()
            altitude = self._spawn_z - z  # 正数=离地高度
            in_air = altitude > _AIR_THRESHOLD
            if self._landed:
                in_air = False

            raw = self._get_raw_state()
            kin = raw.get("kinematics_estimated", {})
            vel = kin.get("linear_velocity", {})
            vn = float(vel.get("x_val", 0.0))
            ve = float(vel.get("y_val", 0.0))
            vd = float(vel.get("z_val", 0.0))

            # 归零坐标（以 spawn 点为原点）
            rel_n = x - self._spawn_x
            rel_e = y - self._spawn_y

            return VehicleState(
                armed=True,
                in_air=in_air,
                mode="PHYSICS",
                position_ned=Position(north=rel_n, east=rel_e, down=-altitude),
                battery_percent=100.0,
                velocity=[vn, ve, vd],
            )
        except Exception as e:
            logger.warning(f"get_state error: {e}")
            return None

    def get_position(self) -> Optional[Position]:
        s = self.get_state()
        return s.position_ned if s else None

    def get_gps(self) -> Optional[GPSPosition]:
        return None

    def get_battery(self) -> tuple:
        return (12.6, 100.0)

    def is_armed(self) -> bool:
        return self._connected

    def is_in_air(self) -> bool:
        if self._landed:
            return False
        return self._get_altitude() > _AIR_THRESHOLD

    # ── 基本飞行操作 ──────────────────────────────────────────────────────────

    def arm(self) -> ActionResult:
        try:
            self._client.arm_disarm(True, self._vehicle_name)
            return ActionResult(success=True, message="Armed")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def disarm(self) -> ActionResult:
        try:
            self._client.arm_disarm(False, self._vehicle_name)
            return ActionResult(success=True, message="Disarmed")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def takeoff(self, altitude: float = 5.0) -> ActionResult:
        """
        使用 AirSim 原生 takeoff API 起飞，然后用 moveByRollPitchYawZ 上升到目标高度。
        altitude: 相对地面高度（米）。
        """
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            self._landed = False
            logger.info(f"Takeoff: native takeoff API -> then rise to {altitude}m")

            # 1. 原生起飞（离地约 3m）
            self._fly_client.takeoff_async_join(timeout_sec=20.0,
                                                vehicle_name=self._vehicle_name)

            # 2. moveByRollPitchYawZ 上升到目标高度
            target_z = self._spawn_z - altitude   # z 减小 = 向上
            self._fly_client.move_by_roll_pitch_yaw_z(
                0.0, 0.0, 0.0, target_z, 5.0, self._vehicle_name
            )

            # 3. 轮询等待到达目标高度（最多 15s）
            deadline = time.time() + 15.0
            while time.time() < deadline:
                _, _, cz = self._get_xyz()
                if abs(cz - target_z) < 0.5:
                    break
                time.sleep(0.2)

            actual_alt = self._get_altitude()
            logger.info(f"Takeoff done: altitude={actual_alt:.1f}m")
            return ActionResult(success=True,
                                message=f"Takeoff OK: {actual_alt:.1f}m altitude")

        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def land(self) -> ActionResult:
        """使用 AirSim 原生 land API 降落。"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            alt = self._get_altitude()
            logger.info(f"Land: calling native land API from {alt:.1f}m")

            self._fly_client.land_async_join(timeout_sec=60.0,
                                             vehicle_name=self._vehicle_name)
            self._landed = True
            final_alt = self._get_altitude()
            logger.info(f"Land confirmed: altitude={final_alt:.1f}m")
            return ActionResult(success=True, message=f"Landed at {final_alt:.1f}m")

        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def fly_to_ned(self, north: float, east: float, down: float,
                   speed: float = 5.0) -> ActionResult:
        """
        飞到指定 NED 坐标（归零坐标，以 spawn 点为原点）。
        安全高度限制：最低 50m（down <= -50）。
        支持外部 request_stop() 打断。
        """
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            # 安全高度
            if down > -_SAFE_ALT:
                logger.warning(
                    f"⚠️ 目标高度 {-down:.0f}m 低于安全高度 {_SAFE_ALT:.0f}m，自动提升"
                )
                down = -_SAFE_ALT

            # 归零坐标 → AirSim 绝对坐标
            abs_x = north + self._spawn_x
            abs_y = east + self._spawn_y
            abs_z = self._spawn_z + down  # down 为负值时 abs_z < spawn_z（向上）

            logger.info(
                f"fly_to_ned: rel({north:.1f},{east:.1f},{down:.1f}) -> "
                f"abs({abs_x:.1f},{abs_y:.1f},{abs_z:.3f})"
            )

            result = self._fly_with_interrupt(
                abs_x, abs_y, abs_z, speed,
                timeout_sec=120.0,
                check_obstacle=True,
            )

            if result == 'ok':
                x, y, z = self._get_xyz()
                err = ((x - abs_x)**2 + (y - abs_y)**2 + (z - abs_z)**2) ** 0.5
                return ActionResult(success=True,
                                    message=f"fly_to_ned OK: err={err:.2f}m")
            elif result == 'stopped':
                return ActionResult(success=False, message="飞行被外部打断，已悬停。")
            elif result == 'collision':
                return ActionResult(success=False, message="⚠️ 发生碰撞，已紧急悬停。")
            elif result == 'obstacle':
                info = self._last_obstacle_info
                dist = info.get('front_dist', 0)
                direction = info.get('direction', '前方')
                return ActionResult(
                    success=False,
                    message=f"⚠️ {direction}{dist:.1f}m 处检测到障碍物，已自动悬停。"
                            "请重新规划航线或改变方向。"
                )
            else:
                return ActionResult(success=False, message=f"fly_to_ned: {result}")

        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def hover(self, duration: float = 5.0) -> ActionResult:
        """悬停指定秒数（用 moveByRollPitchYawZ 保持当前姿态和高度）。"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            logger.info(f"Hover: {duration}s")
            current_yaw = self._get_current_yaw()
            _, _, current_z = self._get_xyz()

            CMD_DURATION = 0.5
            elapsed = 0.0
            while elapsed < duration:
                if self._stop_requested:
                    self._stop_requested = False
                    return ActionResult(success=True,
                                        message=f"Hover aborted at {elapsed:.1f}s")
                remaining = duration - elapsed
                cmd_dur = min(CMD_DURATION, remaining)
                self._fly_client.move_by_roll_pitch_yaw_z(
                    0.0, 0.0, current_yaw, current_z, cmd_dur, self._vehicle_name
                )
                time.sleep(cmd_dur)
                elapsed += cmd_dur

            return ActionResult(success=True, message=f"Hovered {duration}s")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def return_to_launch(self) -> ActionResult:
        """飞回 spawn 点上方，然后降落。"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            # 保持当前高度或至少 50m 飞回 spawn 上方
            alt = max(self._get_altitude(), _SAFE_ALT)
            target_z = self._spawn_z - alt  # 保持高度
            logger.info(
                f"RTL: flying to spawn ({self._spawn_x:.1f},{self._spawn_y:.1f}) "
                f"at z={target_z:.1f}"
            )
            result = self._fly_with_interrupt(
                self._spawn_x, self._spawn_y, target_z, speed=5.0,
                timeout_sec=120.0, check_obstacle=True,
            )
            if result == 'obstacle':
                return ActionResult(success=False, message="RTL: 返航途中遇到障碍物，已悬停")
            if result == 'stopped':
                return ActionResult(success=False, message="RTL: 被外部打断")

            land_result = self.land()
            return ActionResult(
                success=land_result.success,
                message=f"RTL: {land_result.message}",
            )
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def request_stop(self):
        """外部请求停止当前飞行（用户打断 / 安全包线）。"""
        self._stop_requested = True

    # ── 图像接口（从 airsim_adapter.py 移植）────────────────────────────────

    def get_image_base64(self, camera_name: str = 'cam_front') -> Optional[str]:
        """获取指定摄像头图像（base64 JPEG）。"""
        try:
            import base64
            import cv2
            import numpy as np

            responses = self._client.sim_get_images([{
                'camera_name': camera_name,
                'image_type': 0,
                'pixels_as_float': False,
                'compress': False,
            }], vehicle_name=self._vehicle_name)
            if responses:
                r = responses[0]
                h, w = r.get('height', 0), r.get('width', 0)
                data = r.get('image_data_uint8') or r.get('image_data', b'')
                if isinstance(data, str):
                    data = base64.b64decode(data)
                if h > 0 and w > 0 and len(data) >= h * w * 3:
                    img = np.frombuffer(data, dtype=np.uint8).reshape(h, w, 3)
                    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    return base64.b64encode(buf.tobytes()).decode('ascii')
        except Exception as e:
            logger.warning(f'get_image_base64 error: {e}')
        return None
