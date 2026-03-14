# change_altitude -- 改变高度

## 使用时机
需要在当前水平位置上升或下降时使用。

## 参数
- delta: float, 高度变化量(米)
  - 正值=升高, 负值=降低
  - 例如 delta=5 表示升高5米
- speed: float, 升降速度(m/s), 默认 2.0

## 前提条件
- 无人机在空中
- 电池 > 20%

## 执行流程
1. 获取当前位置
2. 计算目标高度 (当前 down - delta)
3. 调用 fly_to_ned 到新高度
4. 等待到达

## 注意事项
- 降低高度时注意地面障碍物
- 最低安全高度建议 2m

## 输出
- new_altitude: float 新高度
- altitude_change: float 实际变化量
