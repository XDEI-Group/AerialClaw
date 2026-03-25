# 飞行安全经验 (Flight Safety Experience)

## 核心经验（从多次任务失败中总结）

### 经验1：永远先了解自己的状态
- 执行任何飞行动作前，先调用 `get_position` 获取当前位置和高度
- 不要假设自己在某个高度，必须确认
- 第一个动作永远是 get_position

### 经验2：高度决定安全
- 城市环境建筑高度范围: 14m ~ 150m
- 安全巡航高度: ≥ 60m（高于绝大部分建筑）
- 靠近高层区域: ≥ 100m
- 观察地面细节: 先到目标上方，再用 change_altitude 降低
- **绝对不要低于 30m 飞行**

### 经验3：fly_to 只管水平移动
- fly_to 给 [north, east] 两个值就够了，高度自动保持
- 如果要改高度，单独用 change_altitude
- 不要在 fly_to 里指定低高度

### 经验4：遇到障碍物的处理
- fly_to 返回"障碍物"错误 → 先 perceive 看什么方向有障碍
- 然后用 fly_relative 绕行或 change_altitude 升高
- 不要重复同一个失败的 fly_to

### 经验5：任务节奏
- 飞到新位置 → observe → report → 再飞
- 不要连续飞多个点不观察
- 每个观察点都 report，操作员需要实时了解情况
