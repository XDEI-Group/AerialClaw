# scan_area -- 区域扫描

## 使用时机
需要获取指定区域的相机图像进行侦察时使用。常作为 detect_object 的前置步骤。

## 参数
- area_center: [x, y, z], 扫描区域中心坐标
- scan_radius: float, 扫描半径(米), 默认 20.0
- camera_id: str, 摄像头ID, 默认 "0"
- vehicle_id: str, 无人机ID, 默认 "UAV_1"

## 前提条件
- 电池 > 15%
- 摄像头正常工作

## 执行流程
1. 优先从 Gazebo 传感器桥接获取真实图像
2. 回退到 AirSim SimManager
3. 最后回退到 mock 模式
4. 返回图像元信息

## 注意事项
- 只返回图像元信息 (shape/id/timestamp), 不返回原始图像数据
- 配合 detect_object 使用完成完整的搜索流程
- scan_radius 描述逻辑扫描范围, 实际依赖相机 FOV 和高度

## 输出
- image_shape: tuple, 图像尺寸 (height, width, channels)
- image_id: str, 图像唯一ID (传给 detect_object)
- timestamp: float, 采集时间戳
- area_info: dict, 区域信息
