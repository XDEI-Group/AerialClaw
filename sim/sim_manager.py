"""
sim_manager.py
仿真管理器 - 统一管理 AirSim 和 PX4 连接，提供仿真环境抽象

功能：
    - 统一管理 AirSim 和 PX4 连接
    - 提供 register_vehicle / get_vehicle_state 接口
    - 将仿真状态同步到 WorldModel
    - 支持多无人机管理

设计原则：
    - sim/ 层作为适配器，不侵入 Brain/Memory 层
    - WorldModel 通过外部注入，不在 sim 层创建

依赖：
    - sim.airsim_bridge: AirSim 桥接器
    - sim.px4_ros2_bridge: PX4 ROS2 桥接器
    - memory.world_model: 世界模型

Author: AerialClaw Team
"""

import time
import logging
import threading
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

# AirSim and PX4 ROS2 bridges are optional — import with fallback
# AirSim 和 PX4 ROS2 桥接为可选依赖，缺失时不影响基础功能
try:
    from sim.airsim_bridge import AirSimBridge, DroneState as AirSimDroneState
except ImportError:
    AirSimBridge = None
    AirSimDroneState = None

try:
    from sim.px4_ros2_bridge import PX4ROS2Bridge, PX4State
except ImportError:
    PX4ROS2Bridge = None
    PX4State = None

logger = logging.getLogger(__name__)


class SimBackend(Enum):
    """仿真后端类型"""
    AIRSIM = "airsim"
    PX4 = "px4"
    HYBRID = "hybrid"  # AirSim + PX4 混合模式


@dataclass
class VehicleState:
    """统一无人机状态数据结构"""
    vehicle_id: str
    vehicle_type: str  # "UAV" | "UGV"
    position: np.ndarray  # [x, y, z] NED
    orientation: np.ndarray  # [roll, pitch, yaw]
    velocity: np.ndarray  # [vx, vy, vz]
    battery: float = 100.0
    armed: bool = False
    flight_state: str = "Landed"  # Landed | TakingOff | Flying | Landing
    timestamp: float = 0.0
    connected: bool = False


class SimManager:
    """
    仿真管理器
    
    统一管理 AirSim 和 PX4 仿真连接，提供：
    - 多无人机注册与状态管理
    - 状态同步到 WorldModel
    - 统一的控制接口
    
    Attributes:
        airsim_bridge: AirSim 桥接器实例
        px4_bridge: PX4 ROS2 桥接器实例
        world_model: 世界模型实例（外部注入）
        vehicles: 已注册的无人机字典
        backend: 当前使用的仿真后端
    """
    
    def __init__(
        self,
        world_model=None,
        backend: SimBackend = SimBackend.PX4,
        airsim_config: Optional[dict] = None,
        px4_config: Optional[dict] = None,
    ):
        """
        初始化仿真管理器
        
        Args:
            world_model: WorldModel 实例，用于状态同步（可选）
            backend: 仿真后端类型
            airsim_config: AirSim 配置字典
            px4_config: PX4 配置字典
        """
        self.world_model = world_model
        self.backend = backend
        
        self.airsim_config = airsim_config or {}
        self.px4_config = px4_config or {}
        
        self.airsim_bridge: Optional[AirSimBridge] = None
        self.px4_bridge: Optional[PX4ROS2Bridge] = None
        
        self.vehicles: dict[str, dict] = {}
        self._vehicles_lock = threading.Lock()
        
        self._initialized = False
        self._running = False
        self._sync_thread: Optional[threading.Thread] = None
        
        logger.info(f"SimManager 初始化，后端模式: {backend.value}")
    
    def initialize(self) -> bool:
        """
        初始化仿真连接
        
        Returns:
            bool: 初始化是否成功
        """
        if self._initialized:
            logger.warning("SimManager 已经初始化")
            return True
        
        success = True
        
        if self.backend in (SimBackend.AIRSIM, SimBackend.HYBRID):
            self.airsim_bridge = AirSimBridge(
                ip=self.airsim_config.get("ip", "127.0.0.1"),
                port=self.airsim_config.get("port", 41451),
                timeout_ms=self.airsim_config.get("timeout_ms", 30000),
            )
            if not self.airsim_bridge.connect():
                logger.error("AirSim 连接失败")
                success = False
            else:
                logger.info("AirSim 连接成功")
        
        if self.backend in (SimBackend.PX4, SimBackend.HYBRID):
            self.px4_bridge = PX4ROS2Bridge(
                node_name="sim_manager_bridge",
                vehicle_name="",
            )
            self.px4_bridge.start_spin()
            
            if not self.px4_bridge.wait_for_connection(timeout=10.0):
                logger.warning("PX4 未连接，将以模拟模式运行")
            else:
                logger.info("PX4 连接成功")
        
        self._initialized = True
        return success
    
    def shutdown(self) -> None:
        """关闭仿真管理器"""
        self._running = False
        
        if self._sync_thread:
            self._sync_thread.join(timeout=2.0)
        
        if self.airsim_bridge:
            self.airsim_bridge.disconnect()
        
        if self.px4_bridge:
            self.px4_bridge.stop_spin()
        
        logger.info("SimManager 已关闭")
    
    def register_vehicle(
        self,
        vehicle_id: str,
        vehicle_type: str,
        initial_position: list = None,
        backend: Optional[SimBackend] = None,
    ) -> bool:
        """
        注册无人机到仿真管理器
        
        Args:
            vehicle_id: 无人机唯一 ID
            vehicle_type: 无人机类型（"UAV" 或 "UGV"）
            initial_position: 初始位置 [x, y, z]
            backend: 指定使用的仿真后端（可选，默认使用管理器配置）
            
        Returns:
            bool: 注册是否成功
        """
        if initial_position is None:
            initial_position = [0, 0, 0]
        
        use_backend = backend or self.backend
        
        vehicle_info = {
            "vehicle_id": vehicle_id,
            "vehicle_type": vehicle_type,
            "position": np.array(initial_position, dtype=np.float64),
            "orientation": np.array([0.0, 0.0, 0.0]),
            "velocity": np.array([0.0, 0.0, 0.0]),
            "battery": 100.0,
            "armed": False,
            "flight_state": "Landed",
            "backend": use_backend,
        }
        
        with self._vehicles_lock:
            if vehicle_id in self.vehicles:
                logger.warning(f"无人机 {vehicle_id} 已注册")
                return True
            
            self.vehicles[vehicle_id] = vehicle_info
        
        if use_backend == SimBackend.AIRSIM and self.airsim_bridge:
            self.airsim_bridge.register_vehicle(vehicle_id)
        
        if self.world_model:
            self.world_model.register_robot(
                robot_id=vehicle_id,
                robot_type=vehicle_type,
                initial_position=initial_position,
            )
        
        logger.info(f"注册无人机 {vehicle_id} (类型: {vehicle_type}, 后端: {use_backend.value})")
        return True
    
    def get_vehicle_state(self, vehicle_id: str) -> Optional[VehicleState]:
        """
        获取无人机当前状态
        
        Args:
            vehicle_id: 无人机 ID
            
        Returns:
            VehicleState: 无人机状态，失败返回 None
        """
        with self._vehicles_lock:
            vehicle_info = self.vehicles.get(vehicle_id)
            if not vehicle_info:
                logger.warning(f"无人机 {vehicle_id} 未注册")
                return None
        
        backend = vehicle_info["backend"]
        
        state = None
        if backend == SimBackend.AIRSIM and self.airsim_bridge:
            airsim_state = self.airsim_bridge.get_vehicle_state(vehicle_id)
            if airsim_state:
                state = self._convert_airsim_state(vehicle_id, vehicle_info, airsim_state)
        
        elif backend == SimBackend.PX4 and self.px4_bridge:
            px4_state = self.px4_bridge.get_state()
            state = self._convert_px4_state(vehicle_id, vehicle_info, px4_state)
        
        return state
    
    def _convert_airsim_state(
        self,
        vehicle_id: str,
        vehicle_info: dict,
        airsim_state: AirSimDroneState,
    ) -> VehicleState:
        """将 AirSim 状态转换为统一格式"""
        return VehicleState(
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_info["vehicle_type"],
            position=airsim_state.position,
            orientation=airsim_state.orientation,
            velocity=airsim_state.linear_velocity,
            battery=100.0,
            armed=airsim_state.armed,
            flight_state=airsim_state.flight_state,
            timestamp=airsim_state.timestamp,
            connected=self.airsim_bridge.connected if self.airsim_bridge else False,
        )
    
    def _convert_px4_state(
        self,
        vehicle_id: str,
        vehicle_info: dict,
        px4_state: PX4State,
    ) -> VehicleState:
        """将 PX4 状态转换为统一格式"""
        return VehicleState(
            vehicle_id=vehicle_id,
            vehicle_type=vehicle_info["vehicle_type"],
            position=px4_state.position,
            orientation=px4_state.attitude,
            velocity=px4_state.velocity,
            battery=px4_state.battery_remaining,
            armed=px4_state.armed,
            flight_state=px4_state.flight_mode,
            timestamp=px4_state.timestamp,
            connected=px4_state.is_connected,
        )
    
    def start_state_sync(self, sync_interval: float = 0.1) -> None:
        """
        启动状态同步线程
        
        Args:
            sync_interval: 同步间隔（秒）
        """
        if self._running:
            logger.warning("状态同步已在运行")
            return
        
        self._running = True
        self._sync_interval = sync_interval
        
        def sync_loop():
            while self._running:
                self._sync_states_to_world_model()
                time.sleep(self._sync_interval)
        
        self._sync_thread = threading.Thread(target=sync_loop, daemon=True)
        self._sync_thread.start()
        logger.info(f"状态同步线程已启动，间隔 {sync_interval}s")
    
    def stop_state_sync(self) -> None:
        """停止状态同步线程"""
        self._running = False
        if self._sync_thread:
            self._sync_thread.join(timeout=2.0)
        logger.info("状态同步已停止")
    
    def _sync_states_to_world_model(self) -> None:
        """同步所有无人机状态到 WorldModel"""
        if not self.world_model:
            return
        
        robot_states = {}
        for vehicle_id in list(self.vehicles.keys()):
            state = self.get_vehicle_state(vehicle_id)
            if state and state.connected:
                robot_states[vehicle_id] = {
                    "position": state.position.tolist(),
                    "battery": state.battery,
                    "status": "executing" if state.armed else "idle",
                    "sensor_status": {
                        "lidar": True,
                        "camera": True,
                    },
                }
        
        if robot_states:
            self.world_model.update_world_state({"robots": robot_states})
    
    def takeoff(self, vehicle_id: str, altitude: float = 10.0) -> bool:
        """
        起飞命令
        
        Args:
            vehicle_id: 无人机 ID
            altitude: 目标高度（米）
            
        Returns:
            bool: 起飞是否成功
        """
        with self._vehicles_lock:
            vehicle_info = self.vehicles.get(vehicle_id)
            if not vehicle_info:
                logger.error(f"无人机 {vehicle_id} 未注册")
                return False
        
        backend = vehicle_info["backend"]
        
        if backend == SimBackend.AIRSIM and self.airsim_bridge:
            return self.airsim_bridge.takeoff(vehicle_id, altitude)
        
        elif backend == SimBackend.PX4 and self.px4_bridge:
            return self.px4_bridge.takeoff(altitude)
        
        return False
    
    def land(self, vehicle_id: str) -> bool:
        """
        降落命令
        
        Args:
            vehicle_id: 无人机 ID
            
        Returns:
            bool: 降落是否成功
        """
        with self._vehicles_lock:
            vehicle_info = self.vehicles.get(vehicle_id)
            if not vehicle_info:
                logger.error(f"无人机 {vehicle_id} 未注册")
                return False
        
        backend = vehicle_info["backend"]
        
        if backend == SimBackend.AIRSIM and self.airsim_bridge:
            return self.airsim_bridge.land(vehicle_id)
        
        elif backend == SimBackend.PX4 and self.px4_bridge:
            return self.px4_bridge.land()
        
        return False
    
    def move_to(
        self,
        vehicle_id: str,
        x: float,
        y: float,
        z: float,
        velocity: float = 5.0,
    ) -> bool:
        """
        移动到指定位置
        
        Args:
            vehicle_id: 无人机 ID
            x, y, z: 目标位置（NED 坐标系）
            velocity: 飞行速度（m/s）
            
        Returns:
            bool: 移动是否成功
        """
        with self._vehicles_lock:
            vehicle_info = self.vehicles.get(vehicle_id)
            if not vehicle_info:
                logger.error(f"无人机 {vehicle_id} 未注册")
                return False
        
        backend = vehicle_info["backend"]
        
        if backend == SimBackend.AIRSIM and self.airsim_bridge:
            return self.airsim_bridge.move_to_position(
                x, y, z, velocity, vehicle_id
            )
        
        elif backend == SimBackend.PX4 and self.px4_bridge:
            self.px4_bridge.start_offboard_mode()
            self.px4_bridge.publish_trajectory_setpoint(
                x=x, y=y, z=-abs(z), yaw=0.0
            )
            return True
        
        return False
    
    def get_camera_image(
        self,
        vehicle_id: str,
        camera_name: str = "0",
    ) -> Optional[np.ndarray]:
        """
        获取相机图像
        
        Args:
            vehicle_id: 无人机 ID
            camera_name: 相机名称
            
        Returns:
            np.ndarray: 图像数据
        """
        if self.airsim_bridge:
            return self.airsim_bridge.get_camera_image(
                camera_name=camera_name,
                vehicle_name=vehicle_id,
            )
        return None
    
    def get_lidar_data(
        self,
        vehicle_id: str,
        lidar_name: str = "Lidar",
    ) -> Optional[np.ndarray]:
        """
        获取激光雷达数据
        
        Args:
            vehicle_id: 无人机 ID
            lidar_name: LiDAR 传感器名称
            
        Returns:
            np.ndarray: 点云数据
        """
        if self.airsim_bridge:
            return self.airsim_bridge.get_lidar_data(
                lidar_name=lidar_name,
                vehicle_name=vehicle_id,
            )
        return None
    
    def get_all_vehicles(self) -> list[str]:
        """
        获取所有已注册的无人机 ID 列表
        
        Returns:
            list[str]: 无人机 ID 列表
        """
        return list(self.vehicles.keys())
    
    def is_ready(self) -> bool:
        """
        检查仿真环境是否就绪
        
        Returns:
            bool: 仿真环境是否就绪
        """
        if not self._initialized:
            return False
        
        if self.backend == SimBackend.AIRSIM:
            return self.airsim_bridge.connected if self.airsim_bridge else False
        
        if self.backend == SimBackend.PX4:
            return self.px4_bridge.is_connected() if self.px4_bridge else False
        
        return True


def create_sim_manager(
    config: dict,
    world_model=None,
) -> SimManager:
    """
    根据配置创建仿真管理器
    
    Args:
        config: 配置字典，包含 backend, airsim, px4 等配置
        world_model: WorldModel 实例
        
    Returns:
        SimManager 实例
    """
    backend_str = config.get("backend", "px4")
    backend = SimBackend(backend_str)
    
    sim_manager = SimManager(
        world_model=world_model,
        backend=backend,
        airsim_config=config.get("airsim", {}),
        px4_config=config.get("px4", {}),
    )
    
    return sim_manager
