# fuse_perception -- 多模态感知融合

## 使用时机
需要将视觉检测结果与激光雷达数据融合, 生成带三维坐标的语义世界状态时使用。
通常在 detect_object 和 LiDAR 扫描之后调用。

## 参数
- detected_objects: list, 来自 detect_object 的检测结果
- lidar_scan: dict, 来自 get_sensor_data 或直接获取的雷达扫描
- robot_pose: [x, y, z, yaw], 机器人当前位姿

## 前提条件
- 电池 > 15%

## 执行流程
1. 解析视觉检测结果
2. 将 LiDAR ranges 转换为极坐标障碍物列表
3. 视觉目标 + LiDAR 距离 -> 世界坐标系三维位置
4. 生成语义世界状态

## 注意事项
- 视觉和雷达的匹配是粗略的 (按序对应)
- 未来会升级为语义级融合 (基于角度重叠检测)
- 优先使用 Gazebo 真实传感器数据

## 输出
- semantic_world_state: dict
  - objects: list, 每项含 label/world_position/confidence
  - free_space_radius: float, 自由空间半径
  - robot_pose: list, 当前位姿
  - source: str, 数据来源
