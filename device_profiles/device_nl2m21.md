# X500 SITL — 设备档案

> 创建时间: 2026-03-15 19:59
> 设备 ID: device_nl2m21

## 基本信息
- 型号: Holybro X500 (PX4 SITL)
- 类型: UAV
- 通信方式: mavlink

## 能力
- fly
- camera
- lidar
- multi_camera

## 传感器
- camera_front
- camera_rear
- camera_left
- camera_right
- camera_down
- lidar_3d

## 物理限制
- max_speed: 10.0
- max_altitude: 120.0
- battery_capacity: simulated
- weight: unknown
- max_payload: 0.0kg

## 备注
PX4 SITL仿真环境，Gazebo Harmonic。激光雷达为gpu_lidar插件，360°×16层点云输出，非真实型号。摄像头5路RGB图像流（前后左右下）。MAVSDK通过UDP 14540连接。纯感知平台，无载荷能力。

## 技能绑定
> 由系统自动管理，设备接入时匹配，退出时挂起

## 经验记录
> 随任务执行自动积累
