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
bash scripts/start_gz_sim.sh urban_rescue

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
参考 `clients/arduino/aerialclaw_client.ino`

**ROS2：**
```bash
ros2 run aerialclaw aerialclaw_bridge \
  --ros-args -p server_url:=http://服务器IP:5001
```

---

## 混合部署

### 边缘节点（Jetson/树莓派）

```bash
# 安装轻量版（不含 VLM、不含前端）
pip install -r requirements-edge.txt

# 配置
# .env 中设置:
#   HYBRID_MODE=edge
#   CLOUD_URL=https://cloud-server:5001
#   LOCAL_MODEL=qwen2.5:1.5b  (本地小模型)

python server.py
```

### 云端节点

```bash
# .env 中设置:
#   HYBRID_MODE=cloud
#   LLM_MODEL=gpt-4o  (强模型)
#   VLM_MODEL=gpt-4o   (视觉模型)

python server.py
```

### 断网策略

混合模式下断网自动触发：
1. 本地小模型接管简单决策
2. 安全包线始终生效（硬编码，不依赖网络）
3. 飞行器自动悬停 → 等待 → 返航

配置 `config/safety_config.yaml`：
```yaml
flight_envelope:
  heartbeat_timeout: 10    # 秒
```

---

## Docker 部署

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN cd ui && npm install && npm run build

EXPOSE 5001
CMD ["python", "server.py"]
```

```bash
# 构建和运行
docker build -t aerialclaw .
docker run -d -p 5001:5001 --env-file .env aerialclaw
```

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
# 命令行
python -m core.doctor

# API
curl http://localhost:5001/api/doctor/run

# Web UI
# 点击 Doctor 面板即可
```

### 日志

- 终端日志: 彩色输出
- 文件日志: `logs/YYYY-MM-DD.log` (7天轮转)
- 审计日志: `logs/audit/` (操作记录)

### 启动自检

`server.py` 启动时自动执行 7 项自检：
- Python 版本
- 依赖完整性
- .env 配置
- LLM 连接
- VLM 连接
- Web UI 构建
- 仿真环境

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
确认 ui/dist/index.html 存在
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
