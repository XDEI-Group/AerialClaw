# BODY.md -- 身体认知文档
# 自动生成于 2026-03-15 18:19:31
# 本文件由系统启动时自动生成，请勿手动编辑。

## 基本信息

- 适配器: px4_mavsdk
- 描述: PX4 SITL via MAVSDK-Python (supports Gazebo, jMAVSim)
- 支持载具类型: multirotor, fixedwing, vtol
- 连接状态: 未连接

## 运动能力

- 类型: 多旋翼无人机 (Multirotor)
- 坐标系: AirSim 世界坐标 (x=北, y=东, z=高度，z越负越高，地面z≈-13)
- 飞行速度: 建议 10-15 m/s, 最大约 30 m/s
- 旋转速度: 最大约 45 deg/s
- 高度范围: 0-120m (受限于仿真环境)
- 定位方式: IMU + 气压计惯性导航 (GPS 信号可能不可用)
- 注意: 长距离飞行可能有位置漂移, 建议用视觉地标校正

## 传感器


## 可用硬技能

- takeoff: 无人机解锁电机并起飞到指定高度。前提：无人机在地面。 [参数: altitude]
- land: 无人机降落到地面。前提：无人机在空中。 [参数: 无]
- fly_to: 飞行到指定 AirSim 世界坐标 [x,y,z]。前提：在空中。z越负越高，地面z≈-13。 [参数: target_position, speed]
- fly_relative: 相对当前位置和朝向移动。使用前/后/左/右/上/下, 单位: 米。例如: forward=10 表示往前飞10米, right=5 表示往右飞5米。多个方向可以同时指定。 [参数: forward, right, up, speed]
- hover: 无人机在当前位置悬停指定时间。前提：无人机必须在空中。 [参数: duration]
- change_altitude: 在当前水平位置上调整飞行高度。前提：无人机必须在空中。打断后想往上飞用这个。 [参数: altitude]
- get_position: 获取无人机当前的 AirSim 世界坐标和 GPS 坐标。 [参数: 无]
- get_battery: 获取无人机电池电压和剩余电量。 [参数: 无]
- return_to_launch: 无人机返回起飞位置并降落。 [参数: 无]
- look_around: 在当前位置原地旋转一圈, 观察四周环境。用于搜索目标、侦察地形。旋转期间 LiDAR 持续扫描。 [参数: duration]
- mark_location: 在当前位置设置标记点, 记录发现的目标或兴趣点。标记会保存到世界模型, 后续可以查看所有标记。 [参数: label, priority]
- get_marks: 查看已设置的所有标记点列表。 [参数: 无]

## 硬件限制

- 电池: 有限续航, 低于 20% 应返航
- 通信: MAVLink UDP, 可能受距离影响
- 载荷: 无额外载荷能力 (仅传感器)
- 天气: 仿真环境无风雨影响, 真实环境需考虑
