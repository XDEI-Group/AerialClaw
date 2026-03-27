# get_position -- 获取当前位置

## 使用时机
需要知道无人机当前位置时使用。常用于规划前的状态确认。
⚠️ 在调用 fly_to 之前必须先调用此技能!

## 参数
无参数。

## 前提条件
- 无人机已连接

## 输出说明
返回的 position 是 AirSim 世界坐标 [x, y, z]:
- x: 北方向（正=北，负=南）
- y: 东方向（正=东，负=西）
- z: 高度，z越负越高！地面z≈-13
  - z=-13 表示在地面
  - z=-43 表示离地30m（-13 - 30 = -43）
  - z=-113 表示离地100m
- altitude: 离地高度（正数，米）
- ground_z: 地面的z值（通常约-13）

## 如何使用返回值
假设返回 position=[15.2, -3.1, -56.0]，ground_z=-13.0，altitude=43.0:
- 当前位置: 北15.2米, 西3.1米, 离地43米
- 如果要保持高度飞到别处，fly_to 的 z 用 -56.0
- 如果要升高到离地80米，change_altitude(altitude=80) 或 fly_to z = -13 - 80 = -93

## 注意事项
- z 是 AirSim 世界坐标，不是相对起飞点
- altitude 字段才是离地高度（正数，米）
- ground_z 字段是地面的世界坐标z值

## 输出
- position: [x, y, z] 世界坐标
- ned: [x, y, z]（同 position，兼容旧字段名）
- altitude: float 离地高度（正数）
- ground_z: float 地面的z坐标（约-13）
- gps: {lat, lon, alt} GPS坐标（如可用）
