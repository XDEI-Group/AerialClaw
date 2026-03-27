"""
airsim_physics.py
物理引擎驱动的 AirSim 适配器（Phase 2）

与 airsim_adapter.py（teleport 版）的关键区别：
  - 用 moveByRollPitchYawZ 实现定向飞行（moveToPosition 在 OpenFly 定制版不可用）
  - 物理引擎驱动飞行，有碰撞检测、真实飞行动力学
  - 无需 hold 线程对抗物理引擎
  - 支持 request_stop() 外部打断正在进行的飞行

坐标系（AirSim NED 世界坐标）：
  x=North, y=East, z=Down（负数=向上）
  直接使用 AirSim 世界绝对坐标，无坐标偏移
  地面 z ≈ -13（连接时自动读取）
"""

import logging
import math
import time
import threading
from typing import Optional

from adapters.sim_adapter import (
    SimAdapter, Position, GPSPosition, VehicleState, ActionResult,
)

logger = logging.getLogger(__name__)

_AIR_THRESHOLD = 1.5   # 离地超过 1.5m 才算在空中


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

        # 地面 z 坐标（连接时从当前位置读取）
        self._ground_z: float = -13.0  # 默认值，连接后自动读取
        # 飞行模式: "teleport"=瞬移插值(演示用,快), "physics"=真实物理飞行(论文验证用)
        # 通过环境变量 FLIGHT_MODE 控制，默认 teleport
        import os as _os
        self._flight_mode = _os.getenv("FLIGHT_MODE", "teleport").lower()

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

    def _get_raw_state_fly(self) -> dict:
        """用 _fly_client 读状态，飞行主循环专用，不和后台安全线程抢连接。"""
        try:
            return self._fly_client.get_multirotor_state(self._vehicle_name) or {}
        except Exception as e:
            logger.warning(f"get_multirotor_state (fly) error: {e}")
            return {}

    def _get_xyz(self) -> tuple:
        """读取 AirSim 绝对世界坐标 (x, y, z)。"""
        raw = self._get_raw_state()
        pos = raw.get("kinematics_estimated", {}).get("position", {})
        return (
            float(pos.get("x_val", 0.0)),
            float(pos.get("y_val", 0.0)),
            float(pos.get("z_val", self._ground_z)),
        )

    def _get_altitude(self) -> float:
        """当前离地高度（米，正数）。AirSim NED: z 越负=越高。"""
        _, _, z = self._get_xyz()
        return self._ground_z - z  # ground_z - z：z比ground_z更负时=正数=离地高度

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
        """紧急悬停：hover + moveByRollPitchYawZ 锁住姿态防自旋。"""
        try:
            self._client.hover_async_join(self._vehicle_name)
        except Exception:
            pass
        # 用 rpyz 锁住当前姿态和高度，防止电机自旋
        try:
            _, _, cz = self._get_xyz()
            yaw = math.degrees(self._get_current_yaw())
            self._fly_client.move_by_roll_pitch_yaw_z(
                0.0, 0.0, yaw, cz, 10.0, self._vehicle_name)
        except Exception as e:
            logger.warning(f"Emergency hover rpyz lock failed: {e}")

    def set_velocity_body(self, forward: float, right: float, down: float,
                          yaw_rate: float = 0) -> ActionResult:
        """
        Body frame 速度控制（驾驶舱操纵杆）。
        直接用 moveByVelocityZ 发速度指令，不再手动映射 pitch/roll 角度。
        body frame (forward/right) 通过 yaw 旋转矩阵转为 NED 世界坐标速度。
        """
        if not self._connected:
            return ActionResult(success=False, message='Not connected')
        try:
            _, _, current_z = self._get_xyz()
            current_yaw = self._get_current_yaw()  # radians

            # Body frame → NED world frame (yaw rotation)
            cos_y = math.cos(current_yaw)
            sin_y = math.sin(current_yaw)
            world_vx = forward * cos_y - right * sin_y  # NED North
            world_vy = forward * sin_y + right * cos_y  # NED East

            CMD_DUR = 0.3
            target_z = current_z + down * CMD_DUR  # down > 0 → z 增大（NED 向下）

            # yaw: 用 yaw_rate 做增量，或保持当前 yaw
            if yaw_rate != 0:
                target_yaw_deg = math.degrees(current_yaw) + yaw_rate * CMD_DUR
                yaw_mode = {'is_rate': True, 'yaw_or_rate': yaw_rate}
            else:
                yaw_mode = {'is_rate': False, 'yaw_or_rate': math.degrees(current_yaw)}

            self._fly_client.move_by_velocity_z(
                world_vx, world_vy, target_z,
                CMD_DUR, self._vehicle_name,
                drivetrain=0,  # MaxDegreeOfFreedom
                yaw_mode=yaw_mode,
            )

            return ActionResult(success=True, message='velocity set')
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def stop_velocity(self) -> ActionResult:
        """停止所有速度指令，保持当前位置悬停。"""
        if not self._connected:
            return ActionResult(success=False, message='Not connected')
        try:
            self._emergency_hover()
            return ActionResult(success=True, message='velocity stopped, hovering')
        except Exception as e:
            return ActionResult(success=False, message=str(e))

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


    def _fly_to_physics(self, target_x: float, target_y: float, target_z: float,
                        speed: float = 10.0, timeout_sec: float = 120.0,
                        check_obstacle: bool = False) -> str:
        """
        真实物理飞行模式（论文验证用）。
        用 moveByRollPitchYawZ 做 PD 位置控制：
          位置误差 → pitch/roll 姿态角 → 物理引擎驱动飞行
        特点：有真实的倾斜、加减速、惯性。
        """
        # ── 控制参数 ──
        Kp = 0.015           # 位置→姿态 P 增益（越大越猛，越小越平滑）
        MAX_ANGLE = 0.35     # 最大倾斜角 rad（约20°）
        ARRIVE_DIST = 5.0    # 到达判定 m
        CMD_DT = 0.1         # 控制周期 s（10Hz）
        SAFE_DIST = 8.0      # 障碍安全距离

        self.is_flying = True
        start_time = time.time()

        # 碰撞检测初始化
        self._collision_flag = False
        self._obstacle_flag = False
        self._obstacle_info = {}
        self._safety_running = True

        def _safety_monitor():
            while self._safety_running:
                try:
                    if self._check_collision():
                        self._collision_flag = True
                except Exception:
                    pass
                if check_obstacle:
                    try:
                        front_dist = self._check_depth('cam_front')
                        if front_dist is not None and front_dist < SAFE_DIST:
                            self._obstacle_info = {'front_dist': front_dist, 'direction': '前方'}
                            self._obstacle_flag = True
                    except Exception:
                        pass
                time.sleep(0.5)

        safety_thread = threading.Thread(target=_safety_monitor, daemon=True)
        safety_thread.start()

        try:
            while True:
                if time.time() - start_time > timeout_sec:
                    logger.warning("fly_physics: timeout")
                    self._emergency_hover()
                    return 'timeout'

                if self._stop_requested:
                    self._stop_requested = False
                    self._emergency_hover()
                    return 'stopped'

                # 读状态
                raw = self._get_raw_state_fly()
                kin = raw.get("kinematics_estimated", {})
                pos = kin.get("position", {})
                cx = float(pos.get("x_val", 0))
                cy = float(pos.get("y_val", 0))
                cz = float(pos.get("z_val", 0))

                # 位置误差
                dx = target_x - cx
                dy = target_y - cy
                dist = math.sqrt(dx*dx + dy*dy)
                dist_3d = math.sqrt(dx*dx + dy*dy + (target_z - cz)**2)

                if dist_3d < ARRIVE_DIST:
                    logger.info(f"fly_physics: arrived (dist={dist_3d:.2f}m)")
                    # 锁姿态悬停
                    yaw = math.degrees(self._get_current_yaw())
                    try:
                        self._fly_client.move_by_roll_pitch_yaw_z(
                            0.0, 0.0, yaw, target_z, 10.0, self._vehicle_name)
                    except Exception:
                        pass
                    self._emergency_hover()
                    return 'ok'

                # PD 控制：位置误差 → pitch/roll
                # pitch 控制南北（dx），负pitch=前进（机头低）
                # roll 控制东西（dy），正roll=向东
                pitch = max(min(-Kp * dx, MAX_ANGLE), -MAX_ANGLE)
                roll  = max(min( Kp * dy, MAX_ANGLE), -MAX_ANGLE)

                # 速度缩放：远处全力，近处减小增益
                if dist < 15.0:
                    scale = max(dist / 15.0, 0.3)
                    pitch *= scale
                    roll *= scale

                # yaw 朝向目标
                if dist > 3.0:
                    yaw_deg = math.degrees(math.atan2(dy, dx))
                else:
                    yaw_deg = math.degrees(self._get_current_yaw())

                # 发送控制指令
                try:
                    self._fly_client.move_by_roll_pitch_yaw_z(
                        roll, pitch, yaw_deg, target_z,
                        CMD_DT * 2, self._vehicle_name)
                except Exception as e:
                    logger.warning(f"moveByRollPitchYawZ error: {e}")

                # 日志（每20帧打一次）
                if int((time.time() - start_time) / CMD_DT) % 20 == 0:
                    logger.info(
                        f"fly_physics: dist={dist:.1f}m 3d={dist_3d:.1f}m "
                        f"pitch={math.degrees(pitch):.1f}° roll={math.degrees(roll):.1f}° "
                        f"yaw={yaw_deg:.0f}° z={cz:.1f}/{target_z:.1f}")

                time.sleep(CMD_DT)

                # 安全检测
                if self._collision_flag:
                    self._collision_flag = False
                    self._emergency_hover()
                    return 'collision'
                if check_obstacle and self._obstacle_flag:
                    info = self._obstacle_info
                    self._obstacle_flag = False
                    self._last_obstacle_info = info
                    self._emergency_hover()
                    return 'obstacle'
        finally:
            self._safety_running = False
            self.is_flying = False

    def _fly_to_with_rpyz(self, target_x: float, target_y: float, target_z: float,
                           speed: float = 5.0, timeout_sec: float = 120.0,
                           check_obstacle: bool = False) -> str:
        """
        瞬移模式（演示用）：直接 simSetVehiclePose 到目标点。
        分多步插值，模拟飞行感，但每步直接到位不依赖物理引擎。
        """
        self.is_flying = True
        try:
            cx, cy, cz = self._get_xyz()
            dx = target_x - cx
            dy = target_y - cy
            dz = target_z - cz
            total_dist = math.sqrt(dx*dx + dy*dy + dz*dz)
            
            # 计算步数：每步移动约 speed*0.3 米
            step_dist = speed * 0.3
            num_steps = max(int(total_dist / step_dist), 1)
            
            logger.info(f"fly_teleport: ({cx:.1f},{cy:.1f},{cz:.1f}) -> ({target_x:.1f},{target_y:.1f},{target_z:.1f}) dist={total_dist:.1f}m steps={num_steps}")
            
            # yaw 朝向目标
            horiz = math.sqrt(dx*dx + dy*dy)
            if horiz > 1.0:
                yaw_rad = math.atan2(dy, dx)
            else:
                yaw_rad = self._get_current_yaw()
            qw = math.cos(yaw_rad / 2)
            qz = math.sin(yaw_rad / 2)
            
            for i in range(1, num_steps + 1):
                if self._stop_requested:
                    self._stop_requested = False
                    self._emergency_hover()
                    return 'stopped'
                
                t = i / num_steps
                nx = cx + dx * t
                ny = cy + dy * t
                nz = cz + dz * t
                
                pose = {
                    "position": {"x_val": nx, "y_val": ny, "z_val": nz},
                    "orientation": {"w_val": qw, "x_val": 0.0, "y_val": 0.0, "z_val": qz},
                }
                try:
                    self._fly_client._rpc.call("simSetVehiclePose", pose, True, self._vehicle_name)
                except Exception as e:
                    logger.warning(f"simSetVehiclePose error: {e}")
                
                time.sleep(0.05)  # 50ms 间隔，看起来像飞行
            
            # 最终精确设置到目标点
            final_pose = {
                "position": {"x_val": target_x, "y_val": target_y, "z_val": target_z},
                "orientation": {"w_val": qw, "x_val": 0.0, "y_val": 0.0, "z_val": qz},
            }
            self._fly_client._rpc.call("simSetVehiclePose", final_pose, True, self._vehicle_name)
            time.sleep(0.1)
            
            # 锁姿态防自旋
            try:
                self._fly_client.move_by_roll_pitch_yaw_z(
                    0.0, 0.0, math.degrees(yaw_rad), target_z, 5.0, self._vehicle_name)
            except Exception:
                pass
            
            logger.info(f"fly_teleport: arrived at ({target_x:.1f},{target_y:.1f},{target_z:.1f})")
            return 'ok'
            
        except Exception as e:
            logger.error(f"fly_teleport error: {e}")
            return 'timeout'
        finally:
            self.is_flying = False


    def _fly_with_interrupt(self, x: float, y: float, z: float, speed: float,
                             timeout_sec: float = 120.0,
                             check_obstacle: bool = False) -> str:
        """飞向目标点，支持外部打断、碰撞检测、深度避障。"""
        if self._flight_mode == "physics":
            return self._fly_to_physics(x, y, z, speed, timeout_sec, check_obstacle)
        else:
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

            # 读取当前位置的 z 作为 GROUND_Z（地面参考高度）
            # 连接时传送到安全高度（保持当前 xy，z 设为地面以上 30m）
            cx, cy, cz = self._get_xyz()
            safe_z = self._ground_z - 30.0  # 地面以上 30m
            if cz > safe_z + 5:  # 如果太低（接近地面或地下）
                logger.info(f"无人机位置过低 (z={cz:.1f})，传送到安全高度 z={safe_z:.1f}")
                import math
                yaw_rad = self._get_current_yaw()
                qw = math.cos(yaw_rad / 2)
                qz_q = math.sin(yaw_rad / 2)
                init_pose = {
                    "position": {"x_val": cx, "y_val": cy, "z_val": safe_z},
                    "orientation": {"w_val": qw, "x_val": 0.0, "y_val": 0.0, "z_val": qz_q},
                }
                try:
                    self._client._rpc.call("simSetVehiclePose", init_pose, True, self._vehicle_name)
                    time.sleep(1.0)
                    logger.info(f"已传送到安全高度: ({cx:.1f}, {cy:.1f}, {safe_z:.1f})")
                except Exception as e:
                    logger.warning(f"传送失败: {e}")
            try:
                raw_state = self._client.get_multirotor_state(self._vehicle_name) or {}
                pos_data = raw_state.get("kinematics_estimated", {}).get("position", {})
                current_z = float(pos_data.get("z_val", -13.0))
                # 不用当前位置作为地面（可能在空中），硬编码上海场景地面 z
                self._ground_z = -13.0
                logger.info(f"Ground z hardcoded: {self._ground_z:.3f}")
            except Exception as e:
                self._ground_z = -13.0
                logger.warning(f"Failed to read ground z, using default -13.0: {e}")

            logger.info(
                f"AirSimPhysics connected: {ip}:{port}, "
                f"ground_z={self._ground_z:.3f}, "
                f"altitude={self._get_altitude():.1f}m"
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
            altitude = self._ground_z - z  # 离地高度（正数）
            in_air = z < self._ground_z - _AIR_THRESHOLD  # z比地面低1.5m以上=在空中

            raw = self._get_raw_state()
            kin = raw.get("kinematics_estimated", {})
            vel = kin.get("linear_velocity", {})
            vn = float(vel.get("x_val", 0.0))
            ve = float(vel.get("y_val", 0.0))
            vd = float(vel.get("z_val", 0.0))

            # 直接使用世界坐标
            return VehicleState(
                armed=True,
                in_air=in_air,
                mode="PHYSICS",
                position_ned=Position(north=x, east=y, down=z),
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
        _, _, z = self._get_xyz()
        return z < self._ground_z - _AIR_THRESHOLD  # z比地面低1.5m以上=在空中

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
            # 读取当前位置作为起始点，target_z = current_z - altitude
            _, _, current_z = self._get_xyz()
            target_z = current_z - altitude  # 从当前位置往上飞 altitude 米
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
        """安全降落：持续向下飞，用 cam_down 深度图检测地面，遇到障碍即判定着陆。"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            _, _, start_z = self._get_xyz()
            logger.info(f"Land: depth-based descent from z={start_z:.2f}")

            LAND_DEPTH_THRESHOLD = 4.0   # cam_down 检测到 < 4m 障碍 = 接近地面
            SLOW_DEPTH_THRESHOLD = 10.0  # < 10m 切慢降
            FAST_STEP = 3.0              # 高空每 tick 下降 3m
            SLOW_STEP = 0.8              # 接近地面每 tick 下降 0.8m
            CMD_DUR = 0.25
            TIMEOUT = 120.0
            MAX_STEPS = 400              # 安全上限

            current_yaw = self._get_current_yaw()
            start_t = time.time()
            step_count = 0

            while time.time() - start_t < TIMEOUT and step_count < MAX_STEPS:
                step_count += 1

                # 外部打断
                if self._stop_requested:
                    self._stop_requested = False
                    logger.warning("🛑 Land: 被外部打断，悬停")
                    self._emergency_hover()
                    return ActionResult(success=False, message="降落被外部打断")

                # cam_down 深度检测
                down_depth = self._check_depth('cam_down')
                if down_depth is not None:
                    logger.debug(f"Land step {step_count}: cam_down depth={down_depth:.1f}m")
                    if down_depth < LAND_DEPTH_THRESHOLD:
                        logger.info(f"Land: 下方障碍 {down_depth:.1f}m < {LAND_DEPTH_THRESHOLD}m，判定着陆")
                        self._emergency_hover()
                        break
                    # 根据下方距离动态调整下降速度
                    step_size = SLOW_STEP if down_depth < SLOW_DEPTH_THRESHOLD else FAST_STEP
                else:
                    # 深度图获取失败，用保守速度下降
                    step_size = SLOW_STEP

                cx, cy, cz = self._get_xyz()
                target_z = cz + step_size  # z 增大 = NED 向下

                try:
                    self._fly_client.move_by_roll_pitch_yaw_z(
                        0.0, 0.0, current_yaw, target_z, CMD_DUR, self._vehicle_name
                    )
                except Exception as e:
                    logger.warning(f"Land descent cmd error: {e}")

                time.sleep(CMD_DUR)

            self._landed = True
            _, _, final_z = self._get_xyz()
            elapsed = round(time.time() - start_t, 1)
            logger.info(f"Land done: z={start_z:.2f} → {final_z:.2f}, steps={step_count}, {elapsed}s")
            return ActionResult(success=True,
                                message=f"Landed (depth-based), {step_count} steps, {elapsed}s")

        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def fly_to_ned(self, north: float, east: float, down: float,
                   speed: float = 5.0) -> ActionResult:
        """
        飞到指定 AirSim 世界坐标（north=x, east=y, down=z）。
        入参直接是世界坐标，不做任何偏移。
        支持外部 request_stop() 打断。
        """
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            # 直接使用世界坐标，无偏移
            abs_x = north
            abs_y = east
            abs_z = down

            logger.info(
                f"fly_to_ned: world({abs_x:.1f},{abs_y:.1f},{abs_z:.3f})"
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

    def change_altitude_relative(self, delta: float, speed: float = 6.0) -> ActionResult:
        """
        纯垂直升降，保持水平位置不变。
        delta > 0 升高，delta < 0 下降（单位：米）。
        用 moveByRollPitchYawZ 保持 roll=0, pitch=0，只改目标 Z。
        """
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            cx, cy, cz = self._get_xyz()
            current_yaw = self._get_current_yaw()

            # delta > 0 升高 → z 更负（NED）
            target_z = cz - delta
            current_alt = self._get_altitude()  # 离地高度（正数）
            target_alt = self._ground_z - target_z  # 目标离地高度

            logger.info(
                f"change_altitude_relative: delta={delta:+.1f}m, "
                f"current_alt={current_alt:.1f}m → target_alt={target_alt:.1f}m, "
                f"cz={cz:.2f} → tz={target_z:.2f}"
            )

            # 安全检查：不能降到地面以下
            if target_alt < 2.0:
                if current_alt < 3.0:
                    msg = f"已在最低安全高度({current_alt:.1f}m)，无法继续下降"
                    logger.warning(f"⚠️ {msg}")
                    return ActionResult(success=False, message=msg)
                logger.warning(f"⚠️ 目标高度 {target_alt:.1f}m 过低，限制到 2m")
                target_z = self._ground_z - 2.0
                target_alt = 2.0

            ARRIVE_DIST = 1.5   # 垂直到达判定（米）
            CMD_DURATION = 0.5
            CHECK_INTERVAL = 0.1
            TIMEOUT = 60.0

            self.is_flying = True
            start_time = __import__('time').time()
            try:
                while True:
                    if __import__('time').time() - start_time > TIMEOUT:
                        logger.warning("change_altitude_relative: timeout")
                        self._emergency_hover()
                        return ActionResult(success=False, message="升降超时")

                    if self._stop_requested:
                        self._stop_requested = False
                        self._emergency_hover()
                        return ActionResult(success=False, message="升降被打断")

                    # 检查是否到达目标高度
                    _, _, cur_z = self._get_xyz()
                    z_err = abs(cur_z - target_z)
                    if z_err < ARRIVE_DIST:
                        logger.info(f"change_altitude_relative: arrived (z_err={z_err:.2f}m)")
                        self._emergency_hover()
                        final_alt = self._ground_z - cur_z
                        return ActionResult(
                            success=True,
                            message=f"高度调整完成: {current_alt:.1f}m → {final_alt:.1f}m (delta={delta:+.1f}m)"
                        )

                    # 保持水平位置，只改 Z
                    self._fly_client.move_by_roll_pitch_yaw_z(
                        0.0, 0.0, current_yaw, target_z, CMD_DURATION, self._vehicle_name
                    )

                    # 等待
                    steps = int(CMD_DURATION / CHECK_INTERVAL)
                    for _ in range(steps):
                        __import__('time').sleep(CHECK_INTERVAL)
                        if self._stop_requested:
                            break
            finally:
                self.is_flying = False

        except Exception as e:
            logger.error(f"change_altitude_relative error: {e}")
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
        """飞回起飞区域（world坐标原点附近）上方，然后降落。"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            # 保持当前高度或至少 5m 飞回原点上方
            alt = max(self._get_altitude(), 5.0)
            target_z = self._ground_z - alt  # 地面以上 alt 米
            logger.info(
                f"RTL: flying to origin (0,0) at z={target_z:.1f}"
            )
            result = self._fly_with_interrupt(
                0.0, 0.0, target_z, speed=5.0,
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
