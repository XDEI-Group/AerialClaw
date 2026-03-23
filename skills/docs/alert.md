# alert -- 异常上报

## 使用时机
发现异常情况（如建筑损坏、火灾痕迹、可疑物体、危险地形）时使用。
警报会以醒目方式推送给操作员。

## 参数
- message: str, 警报内容，描述发现的异常
- level: str, 警报等级 warning/danger/critical，默认 warning

## 注意事项
- 不要滥用 alert，只在真正发现异常时使用
- 常规发现用 report(severity=info)
- alert 是紧急通知，会打断操作员的注意力
- critical 级别意味着可能需要立即中止任务

## 输出
- alert_id: 警报编号
- acknowledged: 是否已送达
