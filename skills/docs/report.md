# report -- 实时巡检报告

## 使用时机
巡检、侦察过程中，每到一个位置观察后，用 report 记录发现。
所有报告会累积，任务结束时自动汇总成完整报告。

## 参数
- content: str, 描述当前位置看到的情况（尽可能详细、包含方位和特征）
- severity: str, 严重程度 info/warning/danger，默认 info

## 执行流程
1. 记录当前位置坐标和时间
2. 追加到累积报告中
3. 实时推送给操作员（操作员会在聊天框看到）

## 最佳实践
- 每个观测点都用 report 记录，不要只在最后汇总
- severity=info 用于常规发现，warning 用于需要注意的情况，danger 用于危险
- content 里包含方位词（前方、左侧、下方等）帮助定位
- 配合 observe 使用：先 observe 看到东西，再 report 记录

## 输出
- report_id: 报告条目编号
- total_entries: 累计报告条目数
