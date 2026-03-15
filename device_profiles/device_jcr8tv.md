# X500 SITL — 设备档案

> 创建时间: 2026-03-15 19:44
> 设备 ID: device_jcr8tv

## 基本信息
- 型号: Holybro X500 (PX4 SITL / Gazebo Harmonic)
- 类型: UAV
- 通信方式: mavlink

## 能力
- fly
- camera
- lidar
- simulation

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
- battery_capacity: simulated (full on takeoff)
- weight: None
- max_payload: None

## 备注
PX4 SITL仿真环境，MAVSDK连接UDP 14540。激光雷达为Gazebo Harmonic gpu_lidar插件，360°×16线，输出PointCloud2点云，非真实型号。5路摄像头覆盖前后左右下五个方向。速度限制由安全包线设定为10m/s。

## 技能绑定
> 由系统自动管理，设备接入时匹配，退出时挂起

## 经验记录
> 随任务执行自动积累
