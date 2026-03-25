# 智能导航 (Smart Navigate)

## 触发条件
当需要飞往较远的目标，途中可能有建筑物或障碍时使用。

## 策略流程

1. **获取位置**: `get_position` 确认起点
2. **感知前方**: `perceive(direction="front", focus="前方飞行路径上有什么障碍？")` 
3. **选择航线**:
   - 前方无障碍 → 直接 `fly_to` 目标
   - 前方有障碍 → 先升高 (`change_altitude`) 或绕行 (`fly_relative`)
4. **分段飞行**: 长距离分成 50-100m 的段，每段检查前方
5. **到达确认**: `get_position` 确认是否到达，`observe` 确认是目标位置

## 遇到障碍的处理
```
前方有障碍?
  → 障碍比我低? → change_altitude(障碍高度+20) → 从上方飞过
  → 障碍比我高? → fly_relative(right=30) 或 fly_relative(left=30) → 绕行
  → 不确定? → perceive(focus="障碍物高度和宽度") → 再决策
```

## 关键原则
- **不要盲飞**: 每段都先看再飞
- **altitude 是最好的朋友**: 不确定就先升高
- **利用 perceive**: 遇到不确定情况，主动提问获取信息
- **记录路线**: 途中发现的地标用 update_map 记录
