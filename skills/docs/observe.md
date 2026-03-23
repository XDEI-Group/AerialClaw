# observe — 相机观察技能

## 概述

抓取无人机前向摄像头图像，返回 base64 编码的 JPEG 图像。

**不依赖 Gazebo `gz` 模块**，直接通过 `SimAdapter.get_image_base64()` 从 AirSim 获取图像。

## 适用场景

- 视觉感知任务（目标检测、场景理解）
- 需要获取当前视野图像时
- 配合 LLM 视觉分析使用

## 输入参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| camera_name | str | front_custom | 摄像头名称（可选，当前实现忽略此参数，由 adapter 决定） |

## 输出字段

| 字段 | 类型 | 说明 |
|------|------|------|
| image_base64 | str \| None | base64 编码的 JPEG 图像，失败时为 None |
| has_image | bool | 是否成功获取图像 |
| source | str | 图像来源：`airsim` / `mock` / `none` |

## 注意事项

1. **不依赖 gz 模块**：本技能通过 AirSim RPC 获取图像，不需要安装 Gazebo Python SDK
2. **has_image=False 不报错**：图像获取失败时 `success=True`，但 `has_image=False`，让 Brain 自行决策
3. **前提条件**：电池 > 10%，无需在空中（地面也可抓图）

## 示例

```python
result = observe_skill.execute({})
if result.output["has_image"]:
    image_data = result.output["image_base64"]
    # 传给视觉模型分析...
```
