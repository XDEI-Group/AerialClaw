# 建筑巡检 (Building Inspect)

## 触发条件
当操作员要求检查某栋建筑的外观状况（窗户、外墙、结构）时使用。

## 策略流程

1. **定位建筑**: `get_position` 确认当前位置，`fly_to` 飞到建筑附近上方
2. **高空全貌**: 在建筑顶部上方 20m，`observe(down)` 俯瞰建筑顶部
3. **四面巡检**: 依次飞到建筑的东/南/西/北四个面，每面 `observe` + `perceive(focus="检查外墙和窗户状况")`
4. **分层检查**: 如果建筑较高，从上到下分 2-3 层高度检查
5. **汇总报告**: 用 `report` 记录每面的检查结果，最后给出总体评估

## 飞行路径
```
建筑顶部上方 → observe(down) 
→ fly_relative(forward=30) 到北面 → observe(front) → perceive(focus="窗户")
→ fly_relative(right=60) 到东面 → observe(front)
→ fly_relative(forward=-60) 到南面 → observe(front)  
→ fly_relative(right=-60) 到西面 → observe(front)
→ 降低 20m → 重复四面（如需要）
→ 返回出发点
```

## 关键原则
- **orbit_inspect 硬技能**优先：如果参数合适，直接用 `orbit_inspect` 一键完成
- **手动绕飞**备选：orbit_inspect 不适用时，用 fly_relative 手动组合
- **focus 要具体**: perceive 时写清楚关注什么（"窗户破损"、"外墙裂缝"、"渗水痕迹"）
- **每面都 report**: 不要攒到最后才汇报
