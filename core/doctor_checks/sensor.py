"""
core/doctor_checks/sensor.py — 传感器健康检查
"""

from __future__ import annotations

from core.doctor import HealthCheck, CheckResult


class CameraCheck(HealthCheck):
    name = "摄像头"
    category = "sensor"

    def check(self) -> CheckResult:
        try:
            from sim.gz_sensor_bridge import get_bridge
            bridge = get_bridge()
            if bridge is None:
                return self._warn("传感器桥接未初始化", "需要启动仿真环境")

            cameras = ["front", "rear", "left", "right", "down"]
            active = []
            for cam in cameras:
                data = bridge.get_camera_data(cam)
                if data and data.get("image"):
                    active.append(cam)

            if len(active) == 5:
                return self._ok(f"5/5 路在线")
            elif len(active) > 0:
                missing = set(cameras) - set(active)
                return self._warn(f"{len(active)}/5 路在线, 缺失: {', '.join(missing)}")
            return self._warn("无摄像头数据", "检查 Gazebo 传感器配置")
        except Exception:
            return self._warn("传感器桥接不可用", "需要启动仿真环境")


class LidarCheck(HealthCheck):
    name = "LiDAR"
    category = "sensor"

    def check(self) -> CheckResult:
        try:
            from sim.gz_sensor_bridge import get_bridge
            bridge = get_bridge()
            if bridge is None:
                return self._warn("传感器桥接未初始化")

            lidar = bridge.get_lidar_data()
            if lidar and lidar.get("count", 0) > 0:
                count = lidar["count"]
                return self._ok(f"在线 ({count} 点/帧)")
            return self._warn("无 LiDAR 数据")
        except Exception:
            return self._warn("LiDAR 不可用", "需要启动仿真环境")


class BatteryCheck(HealthCheck):
    name = "电池"
    category = "sensor"

    def check(self) -> CheckResult:
        try:
            from memory.world_model import WorldModel
            wm = WorldModel.get_instance()
            if wm is None:
                return self._warn("WorldModel 未初始化")

            robots = wm.get_world_snapshot().get("robots", {})
            for rid, rdata in robots.items():
                bat = rdata.get("battery", -1)
                if bat < 0:
                    continue
                if bat < 15:
                    return self._fail(f"{rid}: {bat:.0f}% — 电量危险!", "立即返航或充电")
                if bat < 30:
                    return self._warn(f"{rid}: {bat:.0f}% — 电量偏低")
                return self._ok(f"{rid}: {bat:.0f}%")
            return self._warn("无电池数据")
        except Exception:
            return self._warn("电池状态不可用")
