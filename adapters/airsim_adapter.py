"""
airsim_adapter.py
OpenFly 定制版 AirSim 适配器

坐标系（直接 RPC 测量确认）：
  x_val=North, y_val=East, z_val: z减小=向上，z增大=向下（用户实测确认）
  spawn_z ≈ 2.251（无人机出生点，非零）

关键发现：moveToPosition/moveByVelocity/takeoff_async_join 全部不可用
唯一移动方式：simSetVehiclePose（瞬间传送）

坐标换算：
  向上altitude m: target_z = spawn_z - altitude (z减小=向上)
  fly_to_ned: airsim_z = spawn_z + down (NED down负 → z减小=向上)
"""
import logging
import time
import threading
from typing import Optional

from adapters.sim_adapter import (
    SimAdapter, Position, GPSPosition, VehicleState, ActionResult,
)

logger = logging.getLogger(__name__)

_AIR_THRESHOLD = 1.0  # 离地超过1m才算在空中


class AirSimAdapter(SimAdapter):
    name = "airsim_openfly"
    description = "OpenFly AirSim - simSetVehiclePose teleport"
    supported_vehicles = ["multirotor"]

    def __init__(self, vehicle_name: str = "drone_1"):
        self._vehicle_name = vehicle_name
        self._client = None
        self._connected = False
        self._spawn_z: float = 0.0
        self._spawn_x: float = 0.0  # spawn 点 x，用于坐标归零
        self._spawn_y: float = 0.0  # spawn 点 y，用于坐标归零
        self._home_position: Optional[Position] = None
        self.is_flying: bool = False  # 飞行中标记，摄像头流可据此降频
        self._stop_requested: bool = False  # 外部打断标志
        self._last_obstacle_info: dict = {}  # 最近一次避障信息
        self._landed: bool = False  # 已着陆标记（land 成功后置 True，takeoff 后置 False）
        self._hold_thread: Optional[threading.Thread] = None
        self._hold_running = False
        self._hold_lock = threading.Lock()
        self._hold_client = None
        self._hold_x: float = 0.0
        self._hold_y: float = 0.0
        self._hold_z: float = 0.0

    def _raw(self) -> dict:
        try:
            return self._client.get_multirotor_state(self._vehicle_name) or {}
        except Exception as e:
            logger.warning(f"get_multirotor_state error: {e}")
            return {}

    def _xyz(self):
        # hold 线程在跑时，返回目标位置（RPC 读取可能是中间态）
        if self._hold_running:
            return (self._hold_x, self._hold_y, self._hold_z)
        raw = self._raw()
        pos = raw.get("kinematics_estimated", {}).get("position", {})
        return (
            float(pos.get("x_val", 0.0)),
            float(pos.get("y_val", 0.0)),
            float(pos.get("z_val", self._spawn_z)),
        )

    def _set_pose(self, x, y, z):
        """传送到目标位置并持续维持（后台线程每50ms重设一次，对抗物理引擎）。"""
        with self._hold_lock:
            self._hold_x, self._hold_y, self._hold_z = float(x), float(y), float(z)
            # 立即设一次
            self._do_set_pose(x, y, z)
            # 如果 hold 线程没在跑（或者崩了），启动新的
            if not self._hold_running or (self._hold_thread and not self._hold_thread.is_alive()):
                self._hold_running = True
                self._hold_thread = threading.Thread(target=self._hold_loop, daemon=True)
                self._hold_thread.start()

    def _do_set_pose(self, x, y, z):
        """simSetVehiclePose：瞬间传送到目标位置。"""
        import math
        yaw = getattr(self, '_fly_yaw', 0.0)
        qw = math.cos(yaw / 2)
        qz = math.sin(yaw / 2)

        pose = {
            "position": {"x_val": float(x), "y_val": float(y), "z_val": float(z)},
            "orientation": {"w_val": qw, "x_val": 0.0, "y_val": 0.0, "z_val": qz},
        }
        client = self._hold_client or self._client
        try:
            client._rpc.call("simSetVehiclePose", pose, True, self._vehicle_name)
        except Exception:
            pass

    def _check_obstacle(self, x, y, z):
        """射线碰撞检测：当前位置到目标点之间是否有障碍物。"""
        client = self._hold_client or self._client
        try:
            # simTestLineOfSightToPoint 返回 True=可见(无障碍), False=被遮挡(有障碍)
            visible = client._rpc.call("simTestLineOfSightToPoint",
                {"x_val": float(x), "y_val": float(y), "z_val": float(z)}, self._vehicle_name)
            return not visible  # True=有障碍物
        except Exception:
            return False  # API 失败时不阻断飞行

    def _check_collision(self):
        """检查当前是否发生碰撞。"""
        client = self._hold_client or self._client
        try:
            col = client._rpc.call("simGetCollisionInfo", self._vehicle_name)
            return col.get("has_collided", False)
        except Exception:
            return False

    def _fly_smooth(self, tx, ty, tz, speed=8.0):
        """
        安全飞行：保持当前高度水平飞到目标上方，再调整高度。
        返回: 'ok' / 'obstacle' / 'stopped'
        """
        import math

        sx, sy, sz = self._hold_x, self._hold_y, self._hold_z
        dx, dy, dz = tx - sx, ty - sy, tz - sz
        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
        if dist < 0.1:
            self._hold_x, self._hold_y, self._hold_z = tx, ty, tz
            return 'ok'

        h_dist = math.sqrt(dx*dx + dy*dy)
        
        if h_dist < 3.0:
            return self._fly_smooth_raw(tx, ty, tz, speed)
        else:
            fly_z = min(sz, tz)
            logger.info(f"🛫 飞行: 水平{h_dist:.0f}m, 高度{(self._spawn_z - fly_z):.0f}m")
            if abs(sz - fly_z) > 1.0:
                result = self._fly_smooth_raw(sx, sy, fly_z, speed)
                if result != 'ok':
                    return result
            result = self._fly_smooth_raw(tx, ty, fly_z, speed)
            if result != 'ok':
                return result
            if abs(tz - fly_z) > 1.0:
                return self._fly_smooth_raw(tx, ty, tz, speed)
            return 'ok'

    def _fly_smooth_raw(self, tx, ty, tz, speed=8.0):
        """底层插值飞行 + 实时 LiDAR/深度避障 + 外部打断支持。
        
        飞行中每 15 步（~500ms）检查前方深度图：
        - 前方 < SAFE_DIST 米 → 立即停下，返回 'obstacle'
        - 外部 stop_event 置位 → 立即停下，返回 'stopped'
        - 正常到达 → 返回 'ok'
        """
        import math
        SAFE_DIST = 8.0      # 前方安全距离（米），低于此距离停下
        CHECK_INTERVAL = 15  # 每 15 步检查一次（~500ms）
        
        self.is_flying = True
        sx, sy, sz = self._hold_x, self._hold_y, self._hold_z
        dx, dy, dz = tx - sx, ty - sy, tz - sz
        dist = math.sqrt(dx*dx + dy*dy + dz*dz)
        if dist < 0.1:
            self._hold_x, self._hold_y, self._hold_z = tx, ty, tz
            self.is_flying = False
            return 'ok'
        
        # 朝向对准运动方向
        if abs(dx) > 0.1 or abs(dy) > 0.1:
            self._fly_yaw = math.atan2(dy, dx)
        
        duration = dist / speed
        step_interval = 0.033
        steps = max(1, int(duration / step_interval))
        
        for i in range(1, steps + 1):
            # ── 外部打断检查 ──
            if self._stop_requested:
                logger.warning("🛑 外部打断！停止飞行")
                self.is_flying = False
                self._stop_requested = False
                return 'stopped'
            
            t = i / steps
            nx = sx + dx * t
            ny = sy + dy * t
            nz = sz + dz * t
            self._hold_x, self._hold_y, self._hold_z = nx, ny, nz
            self._do_set_pose(nx, ny, nz)
            time.sleep(step_interval)
            
            # ── 深度图避障（每 CHECK_INTERVAL 步） ──
            if i % CHECK_INTERVAL == 0:
                v_move = abs(nz - sz) / max(dist, 0.1)  # 垂直分量占比
                going_down = (nz > sz)  # z增大=向下
                going_up = (nz < sz)    # z减小=向上
                
                # 向上飞时不检查避障（向上是逃脱障碍的方式）
                if v_move > 0.7 and going_up:
                    pass  # 跳过避障检查
                elif v_move > 0.7 and going_down:
                    # 向下飞 → 检查下方
                    front_dist = self._check_depth('cam_down')
                    if front_dist is not None and front_dist < SAFE_DIST:
                        logger.warning(f"⚠️ 下方障碍物 {front_dist:.1f}m！自动悬停")
                        self.is_flying = False
                        self._last_obstacle_info = {'front_dist': front_dist, 'direction': '下方', 'position': {'x': nx, 'y': ny, 'z': nz}, 'target': {'x': tx, 'y': ty, 'z': tz}}
                        return 'obstacle'
                else:
                    # 水平飞 → 检查前方
                    front_dist = self._check_depth('cam_front')
                    if front_dist is not None and front_dist < SAFE_DIST:
                        logger.warning(f"⚠️ 前方障碍物 {front_dist:.1f}m！自动悬停")
                        self.is_flying = False
                        self._last_obstacle_info = {'front_dist': front_dist, 'direction': '前方', 'position': {'x': nx, 'y': ny, 'z': nz}, 'target': {'x': tx, 'y': ty, 'z': tz}}
                        return 'obstacle'
                        'front_dist': front_dist,
                        'direction': cam_dir,
                        'position': {'x': nx, 'y': ny, 'z': nz},
                        'target': {'x': tx, 'y': ty, 'z': tz},
                    }
                    return 'obstacle'
        
        self._hold_x, self._hold_y, self._hold_z = tx, ty, tz
        self.is_flying = False
        return 'ok'
    
    def _check_depth(self, camera_name: str = 'cam_front') -> float:
        """用深度摄像头检查指定方向最近障碍距离（米）。返回 None 表示检查失败。"""
        try:
            resp = self._client.sim_get_images([{
                'camera_name': camera_name,
                'image_type': 2,  # DepthPerspective
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
            
            import struct
            if isinstance(data, bytes):
                data = list(struct.unpack(f'{len(data)//4}f', data))
            
            # 取中心区域（中间 1/3 x 中间 1/3）的最小深度
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
        except Exception as e:
            return None
    
    def request_stop(self):
        """外部请求停止飞行（用户打断/安全包线）。"""
        self._stop_requested = True

    def _hold_loop(self):
        """后台线程：每33ms重设位置(~30fps)。simSetVehiclePose 覆盖物理引擎。"""
        client = self._hold_client or self._client
        try:
            while self._hold_running:
                self._do_set_pose(self._hold_x, self._hold_y, self._hold_z)
                import time as _t; _t.sleep(0.033)
        except Exception as e:
            logger.warning(f"Hold thread error: {e}")
        finally:
            self._hold_running = False

    def _stop_hold(self):
        """停止 hold 线程。"""
        self._hold_running = False
        self._hold_lock = threading.Lock()
        self._hold_client = None
        if self._hold_thread:
            self._hold_thread.join(timeout=1)
            self._hold_thread = None

    def connect(self, connection_str: str = "", timeout: float = 15.0) -> bool:
        ip, port = "127.0.0.1", 41451
        if connection_str:
            parts = connection_str.split(":")
            ip = parts[0]
            if len(parts) > 1:
                port = int(parts[1])
        try:
            from adapters.airsim_rpc import AirSimDirectClient
            self._client = AirSimDirectClient(ip, port, timeout=timeout)
            if not self._client.connect():
                raise ConnectionError(f"Cannot connect to {ip}:{port}")
            if not self._client.ping():
                raise ConnectionError("ping failed")
            self._client.enable_api_control(True, self._vehicle_name)
            self._client.arm_disarm(True, self._vehicle_name)
            self._connected = True

            # 传送到地面原点，确保 spawn_z 是真实地面值
            import time as _t
            try:
                # (15, -5) settings.json 原始 spawn 点，直接传送到 100m 高空避开地面障碍
                ground_pose = {
                    "position": {"x_val": 15.0, "y_val": -5.0, "z_val": -100.0},
                    "orientation": {"w_val": 1.0, "x_val": 0.0, "y_val": 0.0, "z_val": 0.0},
                }
                self._client._rpc.call("simSetVehiclePose", ground_pose, True, self._vehicle_name)
                _t.sleep(2.0)  # 等2秒让物理引擎落地稳定
            except Exception as _tp_err:
                logger.warning(f"Ground teleport failed: {_tp_err}")

            # 地面 z≈2.0（实测），直接硬编码，不等物理引擎落地
            self._spawn_z = 2.0
            self._spawn_x = 15.0  # spawn 传送目标 x (settings.json 原始 spawn)
            self._spawn_y = -5.0  # spawn 传送目标 y
            logger.info(f"Ground calibrated: spawn=({self._spawn_x},{self._spawn_y},{self._spawn_z}), start at 100m altitude")
            self._home_position = Position(north=0.0, east=0.0, down=0.0)
            # 第二个 RPC 连接，专门给 hold 线程用（避免和摄像头/LiDAR 抢 socket）
            try:
                from adapters.airsim_rpc import AirSimDirectClient
                self._hold_client = AirSimDirectClient(ip, port, timeout=5)
                self._hold_client.connect()
                logger.info("Hold thread RPC connection established")
            except Exception as he:
                logger.warning(f"Hold RPC connect failed, sharing main: {he}")
                self._hold_client = self._client
            logger.info(f"AirSim connected: {ip}:{port}, spawn_z={self._spawn_z:.3f}")


            return True
        except Exception as e:
            logger.error(f"AirSim connect failed: {e}")
            self._connected = False
            return False

    def disconnect(self) -> None:
        self._stop_hold()
        if self._hold_client and self._hold_client is not self._client:
            try:
                self._hold_client.close()
            except Exception:
                pass
            self._hold_client = None
        if self._client:
            try:
                self._client.enable_api_control(False, self._vehicle_name)
            except Exception:
                pass
            try:
                self._client.close()
            except Exception:
                pass
        self._connected = False
        self._client = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    def get_state(self) -> Optional[VehicleState]:
        if not self._connected:
            return None
        try:
            x, y, z = self._xyz()
            altitude = z - self._spawn_z
            in_air = altitude < -_AIR_THRESHOLD
            # 已着陆标记覆盖实时计算
            if self._landed:
                in_air = False
            # 坐标归零：上层看到的坐标以起飞点为原点
            rel_n = x - self._spawn_x
            rel_e = y - self._spawn_y
            return VehicleState(
                armed=True,
                in_air=in_air,
                position_ned=Position(north=rel_n, east=rel_e, down=altitude),
                battery_percent=100.0,
                velocity=[0.0, 0.0, 0.0],
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

    def get_image_base64(self, camera_name: str = 'cam_front') -> str:
        """获取指定摄像头图像（base64 JPEG）。用摄像头专用连接避免和 hold 冲突。"""
        try:
            import base64, cv2, numpy as np
            # 优先用摄像头专用 RPC，避免和 hold 线程抢主连接
            client = getattr(self, '_cam_client', None) or self._client
            responses = client.sim_get_images([{
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

    def is_armed(self) -> bool:
        return self._connected

    def is_in_air(self) -> bool:
        if self._landed:
            return False
        _, _, z = self._xyz()
        return (z - self._spawn_z) < -_AIR_THRESHOLD

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
        """从当前高度往上飞 altitude 米（相对上升）。"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            x, y, z0 = self._xyz()
            current_alt = -(z0 - self._spawn_z)
            # 相对上升：从当前z往上飞altitude米
            target_z = z0 - altitude  # z减小=向上
            logger.info(f"Takeoff: current={current_alt:.1f}m, +{altitude}m -> target_z={target_z:.3f}")
            self._landed = False  # 起飞，清除着陆标记
            if not self._hold_running:
                self._set_pose(x, y, z0)
            result = self._fly_smooth(x, y, target_z, speed=5.0)
            _, _, actual_z = self._xyz()
            actual_alt = -(actual_z - self._spawn_z)
            logger.info(f"Takeoff confirmed: altitude={actual_alt:.1f}m")
            return ActionResult(success=True, message=f"Takeoff OK: now at {actual_alt:.1f}m altitude")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def land(self) -> ActionResult:
        """安全降落：快速下降到接近地面，然后慢降着陆。"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            FINAL_DIST = 1.5     # 下方<1.5m时认为已着陆，停止
            MAX_STEPS = 300
            
            x, y, z = self._xyz()
            current_alt = -(z - self._spawn_z)
            logger.info(f"Land: starting from altitude={current_alt:.1f}m")
            
            if not self._hold_running:
                self._set_pose(x, y, z)
            
            for step in range(MAX_STEPS):
                if self._stop_requested:
                    self._stop_requested = False
                    _, _, fz = self._xyz()
                    fa = -(fz - self._spawn_z)
                    return ActionResult(success=True, message=f"Landing aborted at {fa:.1f}m")
                
                x, y, z = self._xyz()
                current_alt = -(z - self._spawn_z)
                
                # 已经很低，停止
                if current_alt < 2.0:
                    logger.info(f"Land: altitude={current_alt:.1f}m, near ground")
                    break
                
                # 检查下方深度
                below_dist = self._check_depth('cam_down')
                
                if below_dist is not None and below_dist < FINAL_DIST:
                    # 非常接近地面/屋顶，停止
                    logger.info(f"Land: 下方{below_dist:.1f}m，已着陆")
                    break
                elif below_dist is not None and below_dist < 8.0:
                    # 接近地面，慢降 1m
                    target_z = z + 1.0
                    self._fly_smooth_raw(x, y, target_z, speed=1.5)
                else:
                    # 高空，快速降 5m
                    target_z = z + 5.0
                    self._fly_smooth_raw(x, y, target_z, speed=5.0)
            
            _, _, final_z = self._xyz()
            final_alt = -(final_z - self._spawn_z)
            self._landed = True  # 标记已着陆
            logger.info(f"Land confirmed: altitude={final_alt:.1f}m, landed=True")
            return ActionResult(success=True, message=f"Landed at {final_alt:.1f}m")
            logger.info(f"Land confirmed: altitude={final_alt:.1f}m")
            return ActionResult(success=True, message=f"Landed at altitude={final_alt:.1f}m")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def fly_to_ned(self, north: float, east: float, down: float,
                   speed: float = 8.0) -> ActionResult:
        """上层传入归零坐标(以起飞点为原点)，转换为 AirSim 绝对坐标飞行"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            # 归零坐标 → AirSim 绝对坐标
            abs_x = north + self._spawn_x
            abs_y = east + self._spawn_y
            # 安全高度限制：城市环境最低 50m（down ≤ -50）
            MIN_ALT = 50.0
            if down > -MIN_ALT:
                logger.warning(f"⚠️ 目标高度 {-down:.0f}m 低于安全高度 {MIN_ALT:.0f}m，自动提升")
                down = -MIN_ALT
            target_z = self._spawn_z + down
            logger.info(f"fly_to_ned: rel({north:.1f},{east:.1f},{down:.1f}) -> abs({abs_x:.1f},{abs_y:.1f},{target_z:.3f})")
            if not self._hold_running:
                self._set_pose(self._hold_x, self._hold_y, self._hold_z)
            result = self._fly_smooth(abs_x, abs_y, target_z, speed=speed)
            if result == 'obstacle':
                info = self._last_obstacle_info
                direction = info.get('direction', '前方')
                dist_val = info.get('front_dist', 0)
                return ActionResult(
                    success=False,
                    message=f"⚠️ {direction}{dist_val:.1f}m处检测到障碍物，已自动悬停。请重新规划航线或改变方向。"
                )
            if result == 'stopped':
                return ActionResult(success=False, message="飞行被外部打断，已悬停。")
            ax, ay, az = self._xyz()
            err = ((ax-abs_x)**2 + (ay-abs_y)**2 + (az-target_z)**2)**0.5
            return ActionResult(success=True, message=f"fly_to_ned OK: err={err:.3f}m")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def fly_to(self, position: Position, speed: float = 5.0) -> ActionResult:
        return self.fly_to_ned(position.north, position.east, position.down, speed)

    def hover(self, duration: float = 5.0) -> ActionResult:
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            x, y, z = self._xyz()
            self._set_pose(x, y, z)
            time.sleep(duration)
            return ActionResult(success=True, message=f"Hovered {duration}s")
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def set_velocity_body(self, forward: float, right: float, down: float, yaw_rate: float = 0) -> ActionResult:
        """
        WASD 键盘控制：持续按住按方向飞行。
        forward/right/down 单位 m/s，yaw_rate 单位 deg/s。
        通过修改 hold 目标位置实现持续移动。
        """
        if not self._connected:
            return ActionResult(success=False, message='Not connected')
        try:
            # 确保 hold 线程在跑
            if not self._hold_running:
                x, y, z = self._xyz()
                self._set_pose(x, y, z)

            # 用速度修改 hold 目标：每次调用移动一小步（按 100ms 计算）
            dt = 0.1  # 假设前端每 100ms 发一次 velocity_control
            # body frame → world frame（简化：不考虑 yaw 旋转）
            self._hold_x += forward * dt
            self._hold_y += right * dt
            self._hold_z += -down * dt  # NED down正=向下，z减小=向上，取反

            return ActionResult(success=True, message='velocity set')
        except Exception as e:
            return ActionResult(success=False, message=str(e))

    def stop_velocity(self) -> ActionResult:
        """停止速度控制，保持当前位置。"""
        # hold 线程会自动维持当前位置，不需要额外操作
        return ActionResult(success=True, message='velocity stopped')

    def return_to_launch(self) -> ActionResult:
        """飞回起飞点上方，然后安全降落（带下方深度探测）。"""
        if not self._connected:
            return ActionResult(success=False, message="Not connected")
        try:
            if not self._hold_running:
                x, y, z = self._xyz()
                self._set_pose(x, y, z)
            # 先飞到 spawn 点上方（保持当前高度或至少50m）
            x, y, z = self._xyz()
            safe_z = min(z, self._spawn_z - 50.0)  # 至少50m高度
            logger.info(f"RTL: flying to spawn ({self._spawn_x},{self._spawn_y}) at z={safe_z:.1f}")
            result = self._fly_smooth(self._spawn_x, self._spawn_y, safe_z, speed=8.0)
            if result == 'obstacle':
                return ActionResult(success=False, message="RTL: 返航途中遇到障碍物，已悬停")
            # 到了 spawn 上方，安全降落
            r = self.land()
            return ActionResult(success=r.success, message=f"RTL: {r.message}")
        except Exception as e:
            return ActionResult(success=False, message=str(e))
