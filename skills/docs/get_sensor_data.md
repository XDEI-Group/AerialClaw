# get_sensor_data -- 获取传感器数据

## 使用时机
需要原始传感器读数时使用。可获取 IMU、GPS、气压计、LiDAR、摄像头状态。

## 参数
- sensor_types: list, 要获取的传感器类型, 默认 ["imu", "gps", "barometer"]
  - 可选: imu, gps, barometer, lidar, camera
- vehicle_id: str, 无人机ID, 默认 "UAV_1"

## 前提条件
- 电池 > 10%
- 对应传感器已连接

## 执行流程
1. 优先从 Gazebo 传感器桥接获取真实数据
2. 回退到 AirSim SimManager
3. 最后回退到 mock 模式

## 注意事项
- Gazebo 模式下 LiDAR 和摄像头数据为实时数据
- mock 模式返回固定值, 仅用于系统测试
- LiDAR 数据较大, 只返回统计摘要 (ranges_count/min_distance/obstacle_count)

## 输出
- imu_data: dict, 含 orientation/angular_velocity/linear_acceleration
- gps_data: dict, 含 latitude/longitude/altitude/speed/heading
- barometer_data: dict, 含 altitude/pressure/qnh
- lidar_data: dict, 含 ranges_count/min_distance/obstacle_count
- camera_data: dict, 含 width/height/fps/status
- timestamp: float, 数据时间戳
- source: str, 数据来源 (mock/gazebo)
