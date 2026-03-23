"""
adapters/coord.py — NED 坐标统一转换层

统一 NED / ENU / AirSim 坐标系之间的转换，
避免 adapter 里手动做 z = -abs(down) 之类的硬编码。

坐标系说明:
    NED:    North, East, Down（航空标准，z 正 = 向下）
    ENU:    East, North, Up（ROS 常用，z 正 = 向上）
    AIRSIM: x=North, y=East, z=Up（AirSim NED 但 z 轴正 = 向上，即 z = -NED_down）

用法:
    from adapters.coord import CoordTransform, CoordFrame
    x, y, z = CoordTransform.ned_to_airsim(north, east, down)
"""

from enum import Enum


class CoordFrame(Enum):
    """坐标系枚举。"""
    NED = "NED"
    ENU = "ENU"
    AIRSIM = "AIRSIM"


class CoordTransform:
    """坐标系转换工具类。所有方法为静态方法，无状态。"""

    @staticmethod
    def ned_to_airsim(north: float, east: float, down: float):
        """
        NED → AirSim 坐标。
        AirSim: x=North, y=East, z=-Down (向上为负)
        """
        return north, east, -down

    @staticmethod
    def airsim_to_ned(x: float, y: float, z: float):
        """
        AirSim → NED 坐标。
        NED: north=x, east=y, down=-z
        """
        return x, y, -z

    @staticmethod
    def ned_to_enu(n: float, e: float, d: float):
        """
        NED → ENU 坐标。
        ENU: east=e, north=n, up=-d
        """
        return e, n, -d

    @staticmethod
    def enu_to_ned(x: float, y: float, z: float):
        """
        ENU → NED 坐标。
        NED: north=y, east=x, down=-z
        """
        return y, x, -z
