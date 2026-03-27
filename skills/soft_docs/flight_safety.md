# 飞行安全经验 (Flight Safety Experience)

## 核心经验（从多次任务失败中总结）

### 经验1：永远先了解自己的状态
- 执行任何飞行动作前，先调用 `get_position` 获取当前位置
- 查看返回的 position=[x,y,z] 和 ground_z 字段
- 第一个动作永远是 get_position

### 经验2：高度决定安全
- 地面 z ≈ -13（或 ground_z 字段）
- 离地30m: z = -13 - 30 = -43
- 离地100m: z = -13 - 100 = -113
- 安全巡航高度: ≥ 离地60m（z ≤ -73）
- 靠近高层区域: ≥ 离地100m（z ≤ -113）
- **绝对不要低于离地30m飞行（z > -43）**

### 经验3：fly_to 使用世界坐标
- fly_to 给 [x, y, z]，z 必须比地面 z 更负
- 飞到离地H米高: target_z = ground_z - H
- 不知道 ground_z？先 get_position 查看

### 经验4：遇到障碍物的处理
- fly_to 返回"障碍物"错误 → 先 observe 看什么方向有障碍
- 然后用 fly_relative 绕行或 change_altitude 升高
- 不要重复同一个失败的 fly_to

### 经验5：任务节奏
- 飞到新位置 → observe → report → 再飞
- 不要连续飞多个点不观察
- 每个观察点都 report，操作员需要实时了解情况
