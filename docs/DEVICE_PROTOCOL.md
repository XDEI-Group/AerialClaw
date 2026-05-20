# AerialClaw 通用设备协议 v1.0

> AerialClaw 的核心设计：大脑与身体分离。本协议定义了"身体"如何接入"大脑"。

任何设备（无人机、机器狗、机械臂、树莓派、ESP32）只需实现本协议，即可被 AerialClaw 识别、管理和控制。

---

## 目录

- [概述](#概述)
- [通信架构](#通信架构)
- [认证机制](#认证机制)
- [HTTP REST API](#http-rest-api)
- [WebSocket 事件](#websocket-事件)
- [心跳机制](#心跳机制)
- [数据格式](#数据格式)
- [错误码](#错误码)
- [设备端实现指南](#设备端实现指南)

---

## 概述

| 项目 | 说明 |
|------|------|
| 传输协议 | HTTP REST + WebSocket 双通道 |
| 数据格式 | JSON |
| 认证方式 | Token 鉴权（注册时颁发） |
| 心跳间隔 | 5 秒（设备 → 服务端） |
| 超时判定 | 10 秒无心跳 → 标记 offline |
| 编码 | UTF-8 |

### 双通道分工

- **HTTP REST**：设备注册/注销、查询设备列表、一次性状态上报
- **WebSocket**：实时状态推送、传感器数据流、指令下发、心跳

---

## 通信架构

```
┌─────────────┐     HTTP POST /register     ┌──────────────────┐
│   设备端     │ ─────────────────────────→  │   AerialClaw     │
│  (客户端)    │ ←─────────────────────────  │   (服务端)       │
│             │     { token: "xxx" }        │                  │
│             │                             │  DeviceManager   │
│             │     WebSocket connect       │  SafetyManager   │
│             │ ═══════════════════════════ │  FlightEnvelope  │
│             │     device_state (↑)        │  AuditLog        │
│             │     device_sensor (↑)       │                  │
│             │     device_action (↓)       │                  │
│             │     heartbeat (↑↓)          │                  │
└─────────────┘                             └──────────────────┘
```

---

## 认证机制

### 注册流程

1. 设备发送 `POST /api/device/register`，携带设备信息
2. 服务端验证设备信息，生成唯一 Token
3. 设备保存 Token，后续所有请求/WebSocket 连接携带此 Token
4. Token 格式：`ac_<device_id>_<random_hex>`

### Token 使用

**HTTP 请求**：通过 Header 携带
```
Authorization: Bearer ac_drone_01_a1b2c3d4e5f6
```

**WebSocket**：连接时通过查询参数携带
```
ws://host:5001/socket.io/?token=ac_drone_01_a1b2c3d4e5f6
```

---

## HTTP REST API

### 1. 设备注册

```
POST /api/device/register
```

**Request Body:**
```json
{
  "device_id": "drone_01",
  "device_type": "UAV",
  "capabilities": ["fly", "camera", "lidar"],
  "sensors": ["gps", "imu", "barometer", "camera_front", "lidar_2d"],
  "protocol": "http",
  "metadata": {
    "model": "DJI Mavic 3",
    "firmware": "v4.2.1",
    "max_payload": 0.9
  }
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| device_id | string | ✅ | 设备唯一标识，建议格式 `<type>_<seq>` |
| device_type | string | ✅ | `UAV` / `UGV` / `ARM` / `SENSOR` / `CUSTOM` |
| capabilities | list[str] | ✅ | 设备能力列表 |
| sensors | list[str] | ✅ | 传感器列表 |
| protocol | string | ✅ | `mavlink` / `ros2` / `http` / `serial` / `custom` |
| metadata | dict | ❌ | 附加信息（型号、固件等） |

**能力标准词汇表：**

| 能力 | 说明 | 典型设备 |
|------|------|----------|
| `fly` | 飞行 | 无人机 |
| `drive` | 地面移动 | 机器车、机器狗 |
| `grab` | 抓取 | 机械臂 |
| `camera` | 拍照/视频 | 带摄像头的设备 |
| `lidar` | 激光雷达 | 带 LiDAR 的设备 |
| `speak` | 语音输出 | 带扬声器的设备 |
| `listen` | 语音输入 | 带麦克风的设备 |

**Response (201 Created):**
```json
{
  "ok": true,
  "device_id": "drone_01",
  "token": "ac_drone_01_a1b2c3d4e5f6",
  "message": "设备注册成功"
}
```

**Response (409 Conflict - 已注册):**
```json
{
  "ok": false,
  "error": "设备 drone_01 已注册",
  "code": "DEVICE_ALREADY_EXISTS"
}
```

### 2. 设备注销

```
DELETE /api/device/<device_id>
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "ok": true,
  "device_id": "drone_01",
  "message": "设备已注销"
}
```

### 3. 状态上报

```
POST /api/device/<device_id>/state
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "timestamp": 1710489600.123,
  "battery": 75.5,
  "position": {
    "north": 10.5,
    "east": -3.2,
    "down": -5.0
  },
  "status": "idle",
  "in_air": false,
  "armed": false,
  "errors": []
}
```

**字段说明：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| timestamp | float | ✅ | Unix 时间戳 |
| battery | float | ❌ | 电量百分比 0-100 |
| position | dict | ❌ | NED 坐标 {north, east, down} |
| status | string | ❌ | `idle` / `executing` / `error` / `charging` |
| in_air | bool | ❌ | 是否在空中（仅飞行器） |
| armed | bool | ❌ | 是否解锁（仅飞行器） |
| errors | list[str] | ❌ | 当前故障列表 |

**Response (200):**
```json
{
  "ok": true,
  "device_id": "drone_01"
}
```

### 4. 传感器数据上报

```
POST /api/device/<device_id>/sensor
Authorization: Bearer <token>
Content-Type: application/json
```

**Request Body:**
```json
{
  "timestamp": 1710489600.456,
  "sensor_type": "camera",
  "sensor_id": "camera_front",
  "data": {
    "image_base64": "/9j/4AAQ...",
    "width": 640,
    "height": 480,
    "format": "jpeg"
  }
}
```

**传感器数据格式示例：**

```json
// GPS
{
  "sensor_type": "gps",
  "sensor_id": "gps_main",
  "data": {
    "latitude": 34.2517,
    "longitude": 108.9460,
    "altitude": 410.5,
    "accuracy": 1.2,
    "satellites": 12
  }
}

// IMU
{
  "sensor_type": "imu",
  "sensor_id": "imu_main",
  "data": {
    "accel": [0.1, -0.05, -9.81],
    "gyro": [0.01, -0.02, 0.005],
    "mag": [23.5, -5.2, 42.1]
  }
}

// LiDAR
{
  "sensor_type": "lidar",
  "sensor_id": "lidar_2d",
  "data": {
    "ranges": [1.2, 1.5, 2.3, "..."],
    "angle_min": -3.14159,
    "angle_max": 3.14159,
    "range_min": 0.1,
    "range_max": 30.0
  }
}
```

**Response (200):**
```json
{
  "ok": true,
  "device_id": "drone_01"
}
```

### 5. 设备列表

```
GET /api/devices
```

**Response (200):**
```json
{
  "ok": true,
  "devices": [
    {
      "device_id": "drone_01",
      "device_type": "UAV",
      "capabilities": ["fly", "camera", "lidar"],
      "sensors": ["gps", "imu", "camera_front", "lidar_2d"],
      "protocol": "http",
      "status": "online",
      "last_heartbeat": 1710489600.789,
      "state": {
        "battery": 75.5,
        "position": {"north": 10.5, "east": -3.2, "down": -5.0},
        "status": "idle",
        "in_air": false
      }
    }
  ],
  "count": 1
}
```

---

## WebSocket 事件

所有 WebSocket 通信基于 Socket.IO 协议。

### 设备 → 服务端

#### `device_connect`
设备 WebSocket 连接后的首条消息，用于身份认证。

```json
{
  "device_id": "drone_01",
  "token": "ac_drone_01_a1b2c3d4e5f6"
}
```

**服务端响应 `device_connected`：**
```json
{
  "ok": true,
  "device_id": "drone_01",
  "message": "WebSocket 已认证"
}
```

#### `device_state`
实时状态上报（同 HTTP 状态上报格式）。

```json
{
  "device_id": "drone_01",
  "timestamp": 1710489601.123,
  "battery": 74.8,
  "position": {"north": 11.0, "east": -3.0, "down": -5.0},
  "status": "executing"
}
```

#### `device_sensor`
实时传感器数据推送（同 HTTP 传感器上报格式）。

```json
{
  "device_id": "drone_01",
  "timestamp": 1710489601.456,
  "sensor_type": "camera",
  "sensor_id": "camera_front",
  "data": { "image_base64": "...", "width": 640, "height": 480 }
}
```

#### `heartbeat`
设备心跳信号，每 5 秒发送一次。

```json
{
  "device_id": "drone_01",
  "timestamp": 1710489605.000
}
```

**服务端响应 `heartbeat_ack`：**
```json
{
  "device_id": "drone_01",
  "timestamp": 1710489605.001
}
```

### 服务端 → 设备

#### `device_action`
向设备下发指令。

```json
{
  "action_id": "act_20260315_001",
  "device_id": "drone_01",
  "action": "takeoff",
  "params": {
    "altitude": 5.0
  },
  "timeout": 30.0
}
```

**设备响应 `action_result`：**
```json
{
  "action_id": "act_20260315_001",
  "device_id": "drone_01",
  "success": true,
  "message": "起飞至 5.0m",
  "output": {
    "final_altitude": 5.02
  },
  "cost_time": 12.5
}
```

---

## 心跳机制

```
时间轴:
0s    5s    10s    15s    20s
|     |      |      |      |
♥     ♥      ♥      ♥      ♥     ← 正常: 每 5 秒一次心跳
|     |      |      |
♥     ♥      ✗      ✗            ← 异常: 10s 后第 3 次心跳缺失
                    ↓
              标记 offline
              触发安全策略:
              - 飞行器 → 自动悬停
              - 地面车 → 原地停车
              - 机械臂 → 锁定关节
```

### 规则

1. 设备每 **5 秒** 发送一次 `heartbeat` 事件
2. 服务端记录每台设备的 `last_heartbeat` 时间戳
3. 超过 **10 秒** 无心跳 → 标记设备 `offline`
4. 设备 offline 时触发对应的安全策略（由 FlightEnvelope 定义）
5. 设备重新发送心跳 → 自动恢复 `online`

---

## 数据格式

### 统一响应格式

所有 HTTP API 响应遵循统一格式：

**成功：**
```json
{
  "ok": true,
  "data": { ... }
}
```

**失败：**
```json
{
  "ok": false,
  "error": "错误描述",
  "code": "ERROR_CODE"
}
```

### 坐标系

所有位置数据使用 **NED 坐标系**（North-East-Down）：
- `north`: 正北方向（米）
- `east`: 正东方向（米）
- `down`: 向下方向（米），**注意：altitude = -down**

### 时间戳

所有时间戳使用 **Unix 时间戳**（秒，浮点数），如 `1710489600.123`。

---

## 错误码

| 错误码 | HTTP 状态码 | 说明 |
|--------|-------------|------|
| `DEVICE_ALREADY_EXISTS` | 409 | 设备 ID 已注册 |
| `DEVICE_NOT_FOUND` | 404 | 设备未注册或已注销 |
| `DEVICE_OFFLINE` | 503 | 设备离线，无法下发指令 |
| `INVALID_TOKEN` | 401 | Token 无效或已过期 |
| `MISSING_FIELDS` | 400 | 必填字段缺失 |
| `SAFETY_VIOLATION` | 403 | 安全包线拦截（超速/超高等） |
| `ACTION_TIMEOUT` | 504 | 指令执行超时 |
| `APPROVAL_REQUIRED` | 202 | 操作需要人工审批 |

---

## 设备端实现指南

### 最小实现（ESP32/Arduino 级别）

设备端只需实现 4 件事：

1. **注册**：启动时 POST `/api/device/register`
2. **心跳**：每 5 秒通过 WebSocket 发送 `heartbeat`
3. **上报**：状态变化时发送 `device_state`
4. **执行**：收到 `device_action` 后执行并回报 `action_result`

```
设备启动
  │
  ├── POST /register → 获取 token
  │
  ├── WebSocket connect (带 token)
  │
  └── 主循环:
       ├── 每 5s → 发 heartbeat
       ├── 状态变化 → 发 device_state
       ├── 收到 device_action → 执行 → 回报 action_result
       └── 传感器数据 → 发 device_sensor（可选）
```

### 客户端模板状态

当前仓库主要提供服务端协议、适配器接口和示例接入流程。Python / Arduino / ROS2 客户端 SDK 尚未作为生产级包随仓库发布；第三方设备可按本页 REST + WebSocket 协议自行实现轻量客户端。

计划中的 SDK 形态包括：

- Python client package
- Arduino/ESP32 sketch
- ROS2 bridge node

在这些 SDK 发布前，请以本文档中的请求 / 事件 schema 作为接入规范。