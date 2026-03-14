"""
Adapter factory for creating and managing hardware adapters.
Supports dynamic hardware switching and multi-robot systems.
"""

from typing import Dict, Optional, Callable
from adapters.base_adapter import BaseAdapter, RobotType
import logging

logger = logging.getLogger(__name__)


class AdapterFactory:
    """
    Factory for creating and managing hardware adapters.
    
    Example:
        factory = AdapterFactory()
        factory.register("sim", SimAdapter)
        factory.register("real_drone", RealDroneAdapter)
        
        drone = factory.create("sim", "drone_1", RobotType.DRONE, {...})
        car = factory.create("sim", "car_1", RobotType.GROUND_VEHICLE, {...})
    """
    
    _adapters: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, adapter_type: str, adapter_class: type):
        """
        Register an adapter class.
        
        Args:
            adapter_type: Type name (e.g., "sim", "real_drone", "ros2")
            adapter_class: The adapter class (must inherit from BaseAdapter)
        """
        cls._adapters[adapter_type] = adapter_class
        logger.info(f"Registered adapter: {adapter_type} -> {adapter_class.__name__}")
    
    @classmethod
    def create(
        cls,
        adapter_type: str,
        robot_id: str,
        robot_type: RobotType,
        config: Dict,
    ) -> BaseAdapter:
        """
        Create an adapter instance.
        
        Args:
            adapter_type: Type of adapter to create
            robot_id: Unique identifier for the robot
            robot_type: Type of robot (DRONE, GROUND_VEHICLE, etc.)
            config: Configuration dict for the adapter
        
        Returns:
            BaseAdapter instance
        
        Raises:
            ValueError: If adapter_type not registered
        """
        if adapter_type not in cls._adapters:
            raise ValueError(
                f"Adapter type '{adapter_type}' not registered. "
                f"Available: {list(cls._adapters.keys())}"
            )
        
        adapter_class = cls._adapters[adapter_type]
        adapter = adapter_class(robot_id, robot_type, config)
        logger.info(f"Created adapter: {adapter_type} (robot_id={robot_id})")
        return adapter
    
    @classmethod
    def list_adapters(cls) -> list[str]:
        """Return list of registered adapter types"""
        return list(cls._adapters.keys())


class RobotFleet:
    """
    Manages a fleet of robots with different adapters.
    
    Example:
        fleet = RobotFleet()
        fleet.add_robot("drone_1", adapter_drone)
        fleet.add_robot("car_1", adapter_car)
        
        drone_status = fleet.get_status("drone_1")
        all_statuses = fleet.get_all_status()
    """
    
    def __init__(self):
        self.robots: Dict[str, BaseAdapter] = {}
        self.logger = logging.getLogger(__name__)
    
    def add_robot(self, robot_id: str, adapter: BaseAdapter) -> None:
        """Add a robot to the fleet"""
        self.robots[robot_id] = adapter
        self.logger.info(f"Added robot to fleet: {robot_id}")
    
    def remove_robot(self, robot_id: str) -> None:
        """Remove a robot from the fleet"""
        if robot_id in self.robots:
            del self.robots[robot_id]
            self.logger.info(f"Removed robot from fleet: {robot_id}")
    
    def get_robot(self, robot_id: str) -> Optional[BaseAdapter]:
        """Get a specific robot adapter"""
        return self.robots.get(robot_id)
    
    def get_robots_by_type(self, robot_type: RobotType) -> list[BaseAdapter]:
        """Get all robots of a specific type"""
        return [
            adapter for adapter in self.robots.values()
            if adapter.robot_type == robot_type
        ]
    
    def connect_all(self) -> bool:
        """Connect all robots in the fleet"""
        success = True
        for robot_id, adapter in self.robots.items():
            try:
                if adapter.connect():
                    self.logger.info(f"Connected: {robot_id}")
                else:
                    self.logger.error(f"Failed to connect: {robot_id}")
                    success = False
            except Exception as e:
                self.logger.error(f"Exception connecting {robot_id}: {e}")
                success = False
        return success
    
    def disconnect_all(self) -> bool:
        """Disconnect all robots in the fleet"""
        success = True
        for robot_id, adapter in self.robots.items():
            try:
                if adapter.disconnect():
                    self.logger.info(f"Disconnected: {robot_id}")
                else:
                    self.logger.error(f"Failed to disconnect: {robot_id}")
                    success = False
            except Exception as e:
                self.logger.error(f"Exception disconnecting {robot_id}: {e}")
                success = False
        return success
    
    def get_status(self, robot_id: str) -> Optional[Dict]:
        """Get status of a specific robot"""
        adapter = self.get_robot(robot_id)
        if adapter:
            try:
                return adapter.get_status()
            except Exception as e:
                self.logger.error(f"Error getting status for {robot_id}: {e}")
                return {"error": str(e)}
        return None
    
    def get_all_status(self) -> Dict[str, Dict]:
        """Get status of all robots"""
        statuses = {}
        for robot_id in self.robots:
            statuses[robot_id] = self.get_status(robot_id)
        return statuses
    
    def execute_command(self, robot_id: str, command: str, params: Dict) -> bool:
        """Execute a command on a specific robot"""
        adapter = self.get_robot(robot_id)
        if not adapter:
            self.logger.error(f"Robot not found: {robot_id}")
            return False
        
        try:
            return adapter.execute_command(command, params)
        except Exception as e:
            self.logger.error(f"Error executing command on {robot_id}: {e}")
            return False
    
    def list_robots(self) -> list[str]:
        """List all robot IDs in the fleet"""
        return list(self.robots.keys())
