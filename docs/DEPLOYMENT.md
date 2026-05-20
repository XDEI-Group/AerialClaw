# AerialClaw 部署指南

> 从开发环境到生产部署的完整指南。

---

## 目录

- [部署架构](#部署架构)
- [单机部署](#单机部署)
- [分离部署（大脑与身体分离）](#分离部署)
- [混合部署（边缘+云端）](#混合部署)
- [Docker 部署](#docker-部署)
- [安全配置](#安全配置)
- [监控与运维](#监控与运维)
- [常见问题](#常见问题)

---

## 部署架构

AerialClaw 支持三种部署模式：

```
┌─────────────────────────────────────────────────────────┐
│  模式 1: 单机部署                                        │
│  AerialClaw + 仿真环境 运行在同一台机器                    │
│  适合: 开发调试、演示、教学                                │
├─────────────────────────────────────────────────────────┤
│  模式 2: 分离部署（推荐生产环境）                          │
│  AerialClaw(大脑) → 服务器/电脑                           │
│  设备(身体) → 无人机/机器人 + 轻量客户端                    │
│  通信: WiFi / 4G / 串口                                  │
├─────────────────────────────────────────────────────────┤
│  模式 3: 混合部署                                        │
│  边缘(机载 Jetson): 简单决策 + 安全包线                    │
│  云端: 复杂规划 + VLM 分析                                │
│  断网: 自动切换预设安全策略                                 │
└─────────────────────────────────────────────────────────┘
```

---

## 单机部署

### 环境要求

| 项目 | 最低要求 | 推荐 |
|------|---------|------|
| Python | 3.10+ | 3.12 |
| RAM | 4GB | 8GB+ |
| 磁盘 | 2GB | 10GB (含仿真) |
| Node.js | 18+ | 20+ (前端构建) |

### 安装步骤

```bash
# 1. 克隆代码
git clone https://github.com/XDEI-Group/AerialClaw.git
cd AerialClaw

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境
cp .env.example .env
# 编辑 .env，填入 LLM API Key

# 4. 构建前端
cd ui && npm install && npm run build && cd ..

# 5. 启动
python server.py
# 访问 http://localhost:5001
```

### 仿真环境（可选）

```bash
# 安装 PX4 SITL + Gazebo（参考 docs/SIMULATION_SETUP.md）
bash scripts/setup_px4.sh

# 启动仿真
bash scripts/start_sim.sh urban_rescue

# 在另一个终端启动 AerialClaw
python server.py
```

---

## 分离部署

### 架构

```
┌─────────────────┐         ┌─────────────────┐
│   AerialClaw    │  HTTP   │    设备端        │
│   (服务器)      │◄───────►│  (客户端)        │
│                 │  WS     │                 │
│  Brain          │◄═══════►│  Python/Arduino  │
│  Memory         │         │  /ROS2 客户端    │
│  Safety         │         │                 │
│  Web UI         │         │  传感器+执行器    │
└─────────────────┘         └─────────────────┘
```

### 服务端部署

```bash
# 服务器上
python server.py
# 默认监听 0.0.0.0:5001

# 或指定端口
PORT=8080 python server.py
```

### 设备端接入

**Python 设备：**
```python
from aerialclaw_client import AerialClawClient

client = AerialClawClient(
    server_url="http://服务器IP:5001",
    device_id="drone_01",
    device_type="UAV",
    capabilities=["fly", "camera"],
    sensors=["gps", "imu"],
)

client.register()
client.connect_ws()

@client.on_action
def handle(action_id, action, params):
    # 执行指令...
    return True, "完成", {}

# 保持运行
client.wait()
```

**Arduino/ESP32：**
可按 `docs/DEVICE_PROTOCOL.md` 中的 REST + WebSocket schema 实现 Arduino/ESP32 客户端；生产级 SDK 尚未随仓库发布。

**ROS2：**

ROS2 bridge is a planned client SDK target. Until it is shipped, integrate through the REST + WebSocket protocol in `docs/DEVICE_PROTOCOL.md`, or implement a small ROS2 node that forwards telemetry/actions to those endpoints.

---

## 混合部署（研究方向）

Edge/cloud deployment is a research direction rather than a fully packaged distribution in this repository. For now, start from the standard installation and remove heavyweight optional dependencies according to your target hardware.

The safety envelope should remain active in both cloud and edge deployments; do not bypass flight limits when porting to real hardware.

---

## Docker 部署（mock mode）

The root `Dockerfile` is intended for lightweight mock mode review, not PX4/Gazebo simulation.

```bash
docker build -t aerialclaw .
docker run --rm -p 5001:5001 -e SIM_ADAPTER=mock aerialclaw
```

For PX4/Gazebo, use the native setup in `docs/SIMULATION_SETUP.md`.

---

## 安全配置

### 安全等级

| 等级 | 适用场景 | 说明 |
|------|---------|------|
| strict | 新手/演示 | 大部分操作需确认 |
| standard | 日常使用 | 感知自动，控制确认 |
| permissive | 专家/测试 | 大部分自动，仅极危险禁止 |

修改 `config/safety_config.yaml`：
```yaml
safety_level: standard
```

### 四道安全关卡

1. **命令过滤** — 黑名单硬拦截
2. **沙箱隔离** — Docker/subprocess 执行代码
3. **分级审批** — 按操作风险分级
4. **安全包线** — 物理限制硬编码（速度/高度/电量）

安全包线 **不可通过配置关闭**，代码中硬编码：
- 最大速度: 10 m/s
- 最大高度: 120 m
- 最低电量: 15% → 返航, 5% → 降落
- 心跳超时: 10s → 悬停

---

## 监控与运维

### 健康检查

```bash
# Backend status endpoint
curl http://localhost:5001/api/status

# Sensor bridge status
curl http://localhost:5001/api/sensor/status
```

### 日志

- 终端日志: 彩色输出
- 文件日志: runtime log files when file logging is enabled (7天轮转)
- 审计日志: runtime audit logs when audit logging is enabled (操作记录)

### 启动自检

For user smoke testing, run:

```bash
python -m compileall -q adapters brain config llm memory runtime scripts sim skills swarm server.py
python -m pytest
SIM_ADAPTER=mock python server.py
```

---

## 常见问题

### LLM 连接失败
```
检查 .env 中的 LLM_BASE_URL 和 LLM_API_KEY
确保网络可达: curl <LLM_BASE_URL>/models
```

### 前端页面空白
```
cd ui && npm run build
确认前端构建产物已生成
```

### 设备连不上
```
1. 确认服务端 0.0.0.0:5001 可达
2. 检查防火墙是否放行 5001 端口
3. 设备端 server_url 是否正确（不要用 localhost）
```

### 仿真启动失败
```
参考 docs/SIMULATION_SETUP.md
关键: PX4_GZ_STANDALONE=1, Autostart=4001
```
