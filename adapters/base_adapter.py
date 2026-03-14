"""
Base adapter class for all hardware.
Defines the unified interface that all adapters must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
import numpy as np
from enum import Enum


class RobotType(Enum):
    DRONE = "drone"
    GROUND_VEHICLE = "ground_vehicle"
    ARM = "arm"
    SENSOR = "sensor"


@dataclass
class SensorData:
    """Unified sensor data format"""
    timestamp: float
    frame_id: str = "base_link"


@dataclass
class LidarData(SensorData):
    ranges: np.ndarray = None   # [N] distance array
    angles: np.ndarray = None   # [N] angle array
    min_distance: float = 0.0
    max_distance: float = 100.0


@dataclass
class CameraFrame(SensorData):
    image: np.ndarray = None  # HxWx3 or HxWx4
    width: int = 0
    height: int = 0
    camera_matrix: Optional[np.ndarray] = None
    distortion: Optional[np.ndarray] = None


@dataclass
class IMUData(SensorData):
    accel: np.ndarray = None  # [x, y, z] in m/s²
    gyro: np.ndarray = None   # [roll, pitch, yaw] in rad/s
    mag: Optional[np.ndarray] = None  # [x, y, z] in Tesla


@dataclass
class GPSData(SensorData):
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0
    accuracy: float = 0.0


@dataclass
class OdomData(SensorData):
    """Odometry data for ground vehicles"""
    position: np.ndarray = None  # [x, y, z]
    orientation: np.ndarray = None  # [qx, qy, qz, qw] quaternion
    velocity: np.ndarray = None  # [vx, vy, vz]
    angular_velocity: np.ndarray = None  # [wx, wy, wz]


class BaseAdapter(ABC):
    """
    Abstract base class for all hardware adapters.
    Ensures consistent interface across different hardware platforms.
    """
    
    def __init__(self, robot_id: str, robot_type: RobotType):
        self.robot_id = robot_id
        self.robot_type = robot_type
        self.is_connected = False
        self.state = {}  # Current robot state
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the hardware.
        Returns: True if connection successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from the hardware.
        Returns: True if disconnection successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_sensor_data(self) -> Dict[str, SensorData]:
        """
        Get the latest sensor data in unified format.
        Returns dict with keys like "lidar", "camera", "imu", "gps", "odom", etc.
        
        Example:
            {
                "lidar": LidarData(...),
                "camera": CameraFrame(...),
                "imu": IMUData(...),
                "gps": GPSData(...),
            }
        """
        pass
    
    @abstractmethod
    def execute_command(self, command: str, params: Dict[str, Any]) -> bool:
        """
        Execute a control command.
        
        Args:
            command: Command name (e.g., "takeoff", "move_forward", "grab")
            params: Command parameters (e.g., {"height": 5.0})
        
        Returns: True if command executed successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Get the current hardware status.
        Returns dict with status info like battery, position, errors, etc.
        
        Example:
            {
                "battery": 0.75,  # 75% battery
                "position": [100, 200, 5],  # [x, y, z]
                "state": "flying",  # or "idle", "error", etc.
                "errors": [],
            }
        """
        pass
    
    def is_healthy(self) -> bool:
        """Check if hardware is in good condition"""
        status = self.get_status()
        return len(status.get("errors", [])) == 0
    
    def get_capabilities(self) -> list[str]:
        """Return list of available commands for this hardware"""
        return []
