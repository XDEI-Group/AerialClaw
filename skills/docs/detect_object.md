# detect_object -- 目标检测

## 使用时机
需要识别图像中的物体时使用。常用于搜索任务、环境侦察。

## 参数
- image_id: str, 待检测图像ID (来自 scan_area 输出)
- confidence_threshold: float, 置信度过滤阈值, 默认 0.5
  - 精确搜索用 0.7+
  - 广泛扫描用 0.3-0.5

## 前提条件
- 电池 > 10%
- 摄像头正常工作

## 执行流程
1. 获取指定图像数据
2. 运行目标检测模型
3. 按置信度过滤结果
4. 返回结构化检测列表

## 注意事项
- 当前使用 mock 数据, 后续接入 YOLO 模型
- 光线不足时检测精度下降
- 高空拍摄小目标识别率较低, 建议降低高度

## 输出
- detected_objects: list, 每项含 label/confidence/bbox
- object_count: int, 过滤后的目标数量
- source: str, 数据来源 (mock/gazebo)
