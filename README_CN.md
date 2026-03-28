# 🦅 AerialClaw：面向通用自主无人机系统的个性化AI智能体



<p>
  <img src="https://img.shields.io/badge/状态-仿真验证通过-blue" alt="status">
  <img src="https://img.shields.io/badge/许可证-MIT-brightgreen" alt="MIT License">
  <img src="https://img.shields.io/badge/核心-LLM决策-orange" alt="LLM driven">
  <img src="https://img.shields.io/badge/领域-具身智能-black" alt="focus">
  <img src="https://img.shields.io/badge/仿真-PX4+Gazebo-purple" alt="PX4 Gazebo">
  <img src="https://img.shields.io/badge/仿真-OpenFly+AirSim-blue" alt="OpenFly AirSim">
</p>

[English](README.md) | **中文**

**AerialClaw** 是一个面向通用自主无人机系统的个性化AI智能体框架。系统提供标准化的原子动作技能库（起飞、导航、感知等），由大语言模型（LLM）在任务执行中实时感知环境、规划决策并组合调用这些技能——无需为每个任务预编写完整的飞行流程，同时赋予每架无人机独立的身份认知、任务记忆与技能进化能力。

通过 Markdown 文档定义和维护智能体的认知状态与能力边界，由模型自主读写更新，实现真正的"个性化"——每架无人机都拥有属于自己的经验、偏好与成长轨迹。

> *"不预设流程，只定义能力——让每架无人机在任务中自主思考、积累经验、持续成长。"*

<p align="center">
  <img src="assets/console_demo.gif" alt="AerialClaw 控制台 — AI 自主飞行控制" width="720" />
</p>

---

## 📑 目录

- [📢 更新日志](#-更新日志)
- [研究背景与动机](#研究背景与动机)
- [系统架构设计](#系统架构设计)
- [决策机制](#决策机制自主循环实现)
- [技能体系](#已接入的技能体系)
- [感知系统](#感知系统)
- [仿真验证环境](#仿真验证环境)
- [Web 监控界面](#web监控界面)
- [安装与部署](#安装与部署)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [致谢](#致谢)

---

## 📢 更新日志

- **(2026/3/24)** AerialClaw v2.0 更新 — 安全包线、四层记忆、通用设备协议、自进化引擎、AirSim 上海城市场景集成、自主城市巡检演示、GPT-4o 视觉感知、实时地图更新、Doctor Agent 适配器、WASD 手动控制、平滑插值飞行。
- **(2026/3/14)** AerialClaw v1.0 发布 — 完整 Agent 决策循环、12 项硬技能、反思引擎、Web 控制台、PX4+Gazebo 仿真集成。

## 研究背景与动机

当前无人机系统大多依赖预编程脚本，缺乏对未知环境的适应能力。AerialClaw 探索通过 LLM 赋予无人机**自主理解环境与实时决策**的能力：

- 🧠 **推理而非仅执行** — LLM 解析任务目标，生成分步决策
- 👁️ **语义级环境理解** — 多源传感器数据转为自然语言，支持常识推理
- 📝 **飞行经验自积累** — 任务记忆库，基于历史经验优化决策
- 🪪 **能力边界自感知** — 维护性能档案，记录能力边界与表现

## 系统架构设计

<p align="center">
  <img src="assets/architecture.png" alt="AerialClaw 系统架构" width="900" />
</p>

### 核心设计原则

1. **第一人称决策视角** — 以无人机为主体视角进行决策
2. **语义级传感器融合** — 原始传感器数据转换为 LLM 可理解的语义描述
3. **文档驱动技能定义** — 飞行动作与策略以可读文档形式存储，支持动态加载
4. **分层记忆管理机制** — 长期经验积累与短期上下文的高效平衡

## 决策机制：自主循环实现

系统采用基于实时感知的增量决策机制，每一步执行完整的认知循环：

<p align="center">
  <img src="assets/decision_loop_cn.png" alt="自主决策循环" width="600" />
</p>

系统具备基础异常处理能力：路径受阻时重新规划，发现意外目标时调整注意力，电量不足时执行返航。

### 身份与状态管理系统

| 文档 | 功能描述 | 内容示例 |
|------|---------|----------|
| `SOUL.md` | 定义决策偏好与约束 | *安全优先策略，保守风险评估* |
| `BODY.md` | 记录硬件配置与性能参数 | *传感器类型，飞行性能边界* |
| `MEMORY.md` | 存储任务经验与教训 | *特定场景下的有效策略记录* |
| `SKILLS.md` | 跟踪技能执行统计数据 | *各动作的成功率与适用条件* |
| `WORLD_MAP.md` | 构建环境特征知识库 | *已知区域的地标与风险点* |

所有文档采用Markdown格式，支持版本管理与人工审阅。系统在任务前后自动读写相关文档。

### 已接入的技能体系

系统采用**四层技能架构**，灵感来自人类认知结构，每层处理不同抽象级别的能力：

<p align="center">
  <img src="assets/skill_architecture.png" alt="四层技能架构" width="700" />
</p>

**运动技能（12 项原子动作）** — 无人机物理控制：

| 类别 | 技能 | 说明 |
|:---|:---|:---|
| 飞行控制 | `takeoff` `land` `hover` `fly_to` `fly_relative` `change_altitude` `return_to_launch` | 起降、悬停、定点飞行、相对位移、变高、返航 |
| 环境感知 | `look_around` `detect_object` `fuse_perception` | 多方位观察、目标检测（VLM）、多传感器语义融合 |
| 状态查询 | `get_position` `get_battery` | 获取当前位置、电量状态 |
| 标记管理 | `mark_location` `get_marks` | 标记兴趣点、查询已标记位置 |

**认知技能（4 项元技能）** — 信息处理与计算：

| 技能 | 说明 | 安全机制 |
|:---|:---|:---|
| `run_python` | 在沙箱环境中执行 Python 代码 | 自动沙箱（Docker → subprocess → restricted） |
| `http_request` | HTTP GET/POST 请求获取信息 | 内网屏蔽，超时强制 |
| `read_file` | 读取文件内容 | 限制在工作目录 |
| `write_file` | 写入文件内容 | 限制在工作目录，审计记录 |

认知技能赋予 Agent **超越物理动作的信息获取与处理能力** — 例如在规划飞行路径前查询天气 API，或用 Python 计算最优路线。

**软技能（场景策略文档）**：

| 策略 | 说明 |
|:---|:---|
| `search_target` | 区域搜索 — LLM 自主规划搜索路径，融合视觉与雷达判断目标 |
| `rescue_person` | 人员救援 — 发现目标后的接近、评估、标记、上报全流程 |
| `patrol_area` | 区域巡逻 — 按策略覆盖区域，持续监控异常 |

软技能以 Markdown 文档形式存储，LLM 在执行时读取文档理解策略意图，自主组合运动、认知和感知技能完成任务。系统还支持**动态生成新软技能**：当 LLM 在反思中发现重复的行为模式时，会自动提取为新的策略文档。

后续我们计划探索以**技能网络（Skill Network）对软技能的组合与调度进行建模**，使策略选择从纯 LLM 推理逐步演进为可学习、可优化的决策网络。更长远地，我们希望将 AerialClaw 的核心架构解耦为一套**面向通用智能设备的框架**——通过标准化的协议适配层接入各类嵌入式硬件，让任何具备传感与执行能力的设备都能获得同样的自主智能。

### 感知系统

技能的执行离不开对环境的感知。系统采用**被动 + 主动双层感知架构**，为 LLM 的决策提供不同粒度的环境信息：

- **被动感知**（`PerceptionDaemon`）— 后台持续运行，周期性融合多传感器数据生成环境摘要，为 LLM 提供实时态势感知
- **主动感知**（`VLMAnalyzer`）— 由 LLM 按需触发，调用视觉语言模型对图像进行深度分析（目标检测、场景理解等）

感知模型支持**可插拔配置**：可接入云端 API（GPT-4o 等）、本地部署的开源模型、或自行微调的专用模型，以适应不同部署场景对延迟、精度和隐私的需求。

该设计支持研究多种应用场景：
- 🏚️ **灾害响应** — 废墟环境的人员搜救
- 🌲 **生态监测** — 森林区域的异常检测
- 🏗️ **设施巡检** — 建筑结构的安全检查
- 🌾 **农业观测** — 作物生长状态的评估

## 仿真验证环境

目前已在 **AirSim + OpenFly** 仿真环境（上海城市场景）中构建验证平台：

<p align="center">
  <img src="assets/airsim_flight.gif" alt="AirSim 上海城市飞行" width="720" />
  <br>
  <em>上海城市场景自主飞行 — AI 驱动的高楼间导航与实时感知</em>
</p>

| 组件 | 技术选型 |
|------|----------|
| 飞控系统 | AirSim SimpleFlight（API 控制） |
| 仿真环境 | Unreal Engine 4 + OpenFly AirSim（上海城市场景） |
| 传感器模型 | 前向摄像头 + 模拟 LiDAR（360°） |
| 大模型 / 视觉模型 | GPT-4o（规划、感知、报告生成） |
| 通信协议 | AirSim RPC（纯 Socket msgpack） |
| 坐标系 | NED（北-东-地）局部坐标系 |

**仿真场景要素**：高层商业区、中层住宅楼群、低层建筑、城市道路、空旷起降区。

## Web监控界面

<p align="center">
  <img src="assets/ui_overview.png" alt="AerialClaw Web控制界面" width="720" />
</p>

提供研究所需的可视化与交互工具：
- 📷 **多视角视频流** — 前/后/左/右/下五路摄像头实时画面
- 📡 **激光雷达可视化** — 3D LiDAR 点云数据的多层渲染显示
- 🕹️ **手动控制模式** — 支持键盘操控的 FPV 第一人称视角
- 🤖 **AI 自主模式** — 自然语言下达任务，LLM 自主规划执行
- 💬 **指令交互界面** — 自然语言任务指令与对话式交互
- 📊 **状态监控面板** — 飞行参数与系统状态的实时显示
- ⚙️ **模型配置管理** — 支持多 LLM 后端的切换与配置

系统提供**手动 / AI 双模式实时切换**，操作员可随时从 AI 自主模式接管控制权，执行过程中支持一键打断。这是面向真实部署场景的基本安全保障——AI 负责决策，人始终拥有最终否决权。

## 安装与部署

### 环境要求

- Python >= 3.10，Node.js >= 18
- CMake >= 3.22
- Git

### 第一步：克隆仓库

```bash
git clone https://github.com/XDEI-Group/AerialClaw.git
cd AerialClaw
```

### 第二步：Python 环境

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 第三步：构建 Web 界面

```bash
cd ui
npm install
npm run build
cd ..
```

### 第四步：配置 LLM

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 LLM 服务配置：

```bash
ACTIVE_PROVIDER=openai                    # 或 ollama_local / deepseek / moonshot
LLM_BASE_URL=https://api.openai.com/v1   # API 地址
LLM_API_KEY=sk-your-key-here              # API Key
LLM_MODEL=gpt-4o                          # 模型名称
```

支持 OpenAI、DeepSeek、Moonshot、本地 Ollama 等任何兼容 OpenAI 接口的服务。详见 [docs/LLM_CONFIG.md](docs/LLM_CONFIG.md)。

### 第五步：安装 PX4 仿真环境

一键脚本自动完成 PX4 克隆、补丁应用、自定义模型安装和编译：

```bash
./scripts/setup_px4.sh
```

该脚本会自动：
- 克隆 PX4-Autopilot 官方仓库
- 应用 AerialClaw 的参数补丁（磁力计、免遥控器模式等）
- 安装自定义无人机模型（x500_sensor：5 路摄像头 + 3D LiDAR）
- 安装自定义 Gazebo 场景（urban_rescue）
- 编译 PX4 SITL

> 首次编译约需 10-30 分钟。macOS ARM64 用户如遇问题，参见 [docs/SIMULATION_SETUP.md](docs/SIMULATION_SETUP.md)。

## 快速开始

按顺序启动四个终端：

**终端 1 — 仿真环境**
```bash
cd ../PX4-Autopilot
export CMAKE_POLICY_VERSION_MINIMUM=3.5
export PX4_GZ_WORLD=urban_rescue
make px4_sitl gz_x500
```

**终端 2 — MAVSDK 服务**
```bash
mavsdk_server -p 50051 udp://:14540
```

**终端 3 — AerialClaw 主服务**
```bash
cd AerialClaw
source venv/bin/activate
python server.py
```

**终端 4 — 浏览器访问**
```
http://localhost:5001
```

在 Web 界面中：
1. 点击「⚡ 初始化系统」
2. 右上角切换到「🤖 AI」模式
3. 输入自然语言指令测试：
   - *"起飞至15米高度并观察周围环境"*
   - *"搜索北部区域，发现目标后拍照记录"*
   - *"报告当前电量和位置"*

## 项目结构

```
AerialClaw/
├── server.py                    # 服务入口（REST + WebSocket）
├── config.py                    # 全局配置（从 .env 读取）
├── llm_client.py                # LLM 多 Provider 客户端
├── requirements.txt             # Python 依赖
│
├── brain/                       # 认知决策层
│   ├── agent_loop.py            #   自主决策循环
│   ├── planner_agent.py         #   LLM 任务规划器（记忆感知）
│   └── chat_mode.py             #   对话模式
│
├── core/                        # 核心系统（v2.0）
│   ├── preflight.py             #   7 项启动自检
│   ├── doctor.py                #   健康评分系统（0-100）
│   ├── doctor_checks/           #   连接 / 传感器 / AI / 配置检查
│   ├── errors.py                #   10 个异常类 + 修复提示
│   ├── logger.py                #   彩色终端 + 7 天文件轮转
│   ├── device_manager.py        #   通用设备注册中心
│   ├── device_analyzer.py       #   LLM 设备能力推断
│   ├── device_onboarding.py     #   对话式设备建档
│   ├── code_generator.py        #   自动适配器代码生成
│   ├── skill_binder.py          #   能力 → 技能匹配
│   ├── skill_evolver.py         #   技能优化引擎
│   ├── system_executor.py       #   沙箱代码执行
│   ├── capability_gap.py        #   三层能力缺口检测
│   ├── bootstrap.py             #   系统引导编排
│   ├── nlu_engine.py            #   自然语言理解
│   ├── hybrid_planner.py        #   端云混合规划
│   ├── transport.py             #   多协议传输层
│   ├── failsafe.py              #   故障安全状态机
│   ├── body_sense/              #   实时硬件感知引擎
│   └── safety/                  #   脊髓安全架构
│       ├── command_filter.py    #     命令白名单过滤
│       ├── sandbox.py           #     自动降级沙箱（Docker→subprocess→restricted）
│       ├── approval.py          #     人工审批
│       ├── flight_envelope.py   #     硬编码物理限制
│       └── audit_log.py         #     不可篡改审计日志
│
├── perception/                  # 感知系统
│   ├── daemon.py                #   被动感知守护线程
│   ├── vlm_analyzer.py          #   主动视觉分析（云端 VLM）
│   ├── prompts.py               #   感知提示词
│   └── gz_camera.py             #   Gazebo 摄像头桥接
│
├── skills/                      # 四层技能架构
│   ├── motor_skills.py          #   运动层：起飞、降落、飞行、悬停
│   ├── perception_skills.py     #   感知层：检测、观察、扫描
│   ├── cognitive_skills.py      #   认知层：HTTP 请求、Python 执行
│   ├── soft_skills.py           #   策略层：文档驱动组合
│   ├── soft_docs/               #   软技能策略文档（Markdown）
│   ├── hard_skills.py           #   硬技能兼容接口
│   ├── registry.py              #   技能注册中心（即插即用）
│   ├── skill_loader.py          #   动态技能加载
│   ├── dynamic_skill_gen.py     #   运行时技能生成
│   └── docs/                    #   技能文档（13 项）
│
├── memory/                      # 四层记忆系统
│   ├── memory_manager.py        #   记忆编排器
│   ├── episodic_memory.py       #   情节记忆（任务历史）
│   ├── skill_memory.py          #   技能记忆（执行统计）
│   ├── world_model.py           #   世界模型（环境状态）
│   ├── vector_store.py          #   向量语义检索
│   ├── shared_memory.py         #   跨设备共享记忆
│   ├── reflection_engine.py     #   任务后反思（LLM）
│   ├── skill_evolution.py       #   技能进化追踪
│   └── task_log.py              #   结构化任务日志
│
├── adapters/                    # 硬件抽象层
│   ├── base_adapter.py          #   抽象接口（所有设备）
│   ├── protocol_adapter.py      #   通用设备协议（REST+WS）
│   ├── adapter_manager.py       #   多设备适配器管理
│   ├── adapter_factory.py       #   适配器自动创建
│   ├── px4_adapter.py           #   PX4 SITL + MAVSDK
│   ├── airsim_adapter.py        #   AirSim 远程连接
│   ├── sim_adapter.py           #   仿真基础适配器
│   └── mock_adapter.py          #   Mock 测试适配器
│
├── robot_profile/               # 身份文档
│   ├── SOUL.md / BODY.md        #   人格与硬件描述
│   ├── MEMORY.md / SKILLS.md    #   经验与技能自述
│   ├── WORLD_MAP.md             #   环境地图
│   └── body_generator.py        #   从在线设备自动生成 BODY.md
│
├── device_profiles/             # 设备能力档案（每设备独立 Markdown）
│
├── clients/                     # 多平台客户端 SDK
│   ├── python/                  #   Python 客户端库
│   ├── arduino/                 #   Arduino/ESP32 客户端
│   └── ros2/                    #   ROS2 桥接节点
│
├── sim/                         # 仿真资源
│   ├── models/                  #   自定义 Gazebo 模型
│   ├── worlds/                  #   自定义 Gazebo 场景
│   ├── airframes/               #   自定义 airframe
│   └── sim_manager.py           #   仿真生命周期管理
│
├── simulator/                   # 独立仿真客户端
│   ├── sim_client.py            #   解耦仿真设备客户端
│   └── start_sim.sh             #   一键启动仿真
│
├── ui/                          # Web 监控界面（React）
│   └── src/components/          #   15 个 React 组件
│
├── docs/                        # 开发文档
│   ├── ARCHITECTURE.md          #   系统架构
│   ├── FAQ.md                   #   12 个已知问题 + 解决方案
│   └── ...                      #   搭建、适配器、技能、感知指南
│
└── assets/                      # 图片与演示资源
```

## 研究进展与计划

### 已实现（v2.0）
- [x] 自主决策循环 · 身份与状态管理 · 四层技能架构
- [x] 被动 + 主动双层感知 · 经验积累与反思 · 动态技能生成
- [x] PX4 + Gazebo 仿真集成 · Web 监控与交互界面（15 个组件）
- [x] 脊髓安全架构 — 命令过滤 → 沙箱 → 审批 → 安全包线
- [x] 四层记忆系统 — 工作 / 情节 / 技能 / 世界 + 向量检索
- [x] 通用设备协议 — REST + WebSocket，任何设备可接入
- [x] 自进化引擎 — 设备分析 → 代码生成 → 技能优化
- [x] 设备生命周期 — 对话建档 → 能力画像 → 技能绑定
- [x] 混合部署 — 端云协同规划，自动故障切换
- [x] 多平台客户端 — Python SDK、Arduino/ESP32、ROS2 桥接
- [x] AirSim 适配器 — 远程仿真连接支持
- [x] AirSim 远程仿真验证 — 上海城市场景自主飞行验证通过

### 未来方向
- [ ] 真实无人机移植 · Sim2Real 迁移
- [ ] 多智能体协作 · MCP 标准接口 · 跨设备共享学习

## 参与贡献

欢迎 Issue 和 PR。详见 [docs/](docs/) 中的开发文档。

## 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

## 致谢

项目由西安电子科技大学计算机科学与技术学院 ROBOTY 实验室开发。

研究思路受到 [OpenClaw](https://github.com/openclaw/openclaw) 项目的启发，在此表示感谢。

基于以下开源技术构建：
[PX4](https://px4.io/) · [Gazebo](https://gazebosim.org/) · [MAVSDK](https://mavsdk.mavlink.io/) · [React](https://react.dev/) · [Vite](https://vitejs.dev/)

---

*本项目为学术研究性质的开源项目，旨在探索LLM在自主移动平台中的应用潜力。*