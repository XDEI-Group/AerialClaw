# get_position -- 获取当前位置

## 使用时机
需要知道无人机当前位置时使用。常用于规划前的状态确认。

## 参数
无参数。

## 前提条件
- 无人机已连接

## 注意事项
- 返回 NED 本地坐标 (相对起飞点)
- GPS 弱信号环境下位置可能有漂移

## 输出
- ned: [north, east, down] NED坐标
- gps: [lat, lon, alt] GPS坐标 (如可用)
- altitude: float 海拔高度
