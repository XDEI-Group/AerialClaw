# 🦅 AerialClaw：面向通用自主无人机系统的个性化AI智能体



<p>
  <img src="https://img.shields.io/badge/状态-仿真验证通过-blue" alt="status">
  <img src="https://img.shields.io/badge/许可证-MIT-brightgreen" alt="MIT License">
  <img src="https://img.shields.io/badge/核心-LLM决策-orange" alt="LLM driven">
  <img src="https://img.shields.io/badge/领域-具身智能-black" alt="focus">
  <img src="https://img.shields.io/badge/仿真-PX4+Gazebo-purple" alt="PX4 Gazebo">
</p>

[English](README.md) | **中文**

**AerialClaw** 是一个面向通用自主无人机系统的个性化AI智能体框架。系统提供标准化的原子动作技能库（起飞、导航、感知等），由大语言模型（LLM）在任务执行中实时感知环境、规划决策并组合调用这些技能——无需为每个任务预编写完整的飞行流程，同时赋予每架无人机独立的身份认知、任务记忆与技能进化能力。

通过 Markdown 文档定义和维护智能体的认知状态与能力边界，由模型自主读写更新，实现真正的"个性化"——每架无人机都拥有属于自己的经验、偏好与成长轨迹。

> *"不预设流程，只定义能力——让每架无人机在任务中自主思考、积累经验、持续成长。"*

<p align="center">
  <img src="assets/demo.gif" alt="AerialClaw 演示" width="720" />
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

系统采用**硬技能 + 软技能**的两级架构。硬技能是直接操控无人机的原子动作，软技能是由 LLM 阅读文档后自主组合硬技能来执行的高级策略。

**硬技能（12 项原子动作）**：

| 类别 | 技能 | 说明 |
|:---|:---|:---|
| 飞行控制 | `takeoff` `land` `hover` `fly_to` `fly_relative` `change_altitude` `return_to_launch` | 起降、悬停、定点飞行、相对位移、变高、返航 |
| 环境感知 | `look_around` `detect_object` `fuse_perception` | 多方位观察、目标检测（VLM）、多传感器语义融合 |
| 状态查询 | `get_position` `get_battery` | 获取当前位置、电量状态 |
| 标记管理 | `mark_location` `get_marks` | 标记兴趣点、查询已标记位置 |

**软技能（场景策略文档）**：

| 策略 | 说明 |
|:---|:---|
| `search_target` | 区域搜索 — LLM 自主规划搜索路径，融合视觉与雷达判断目标 |
| `rescue_person` | 人员救援 — 发现目标后的接近、评估、标记、上报全流程 |
| `patrol_area` | 区域巡逻 — 按策略覆盖区域，持续监控异常 |

软技能以 Markdown 文档形式存储，LLM 在执行时读取文档理解策略意图，自主组合硬技能完成任务。系统还支持**动态生成新软技能**：当 LLM 在反思中发现重复的行为模式时，会自动提取为新的策略文档。后续我们计划探索以**技能网络（Skill Network）对软技能的组合与调度进行建模**，使策略选择从纯 LLM 推理逐步演进为可学习、可优化的决策网络。更长远地，我们希望将 AerialClaw 的核心架构解耦为一套**面向通用智能设备的框架**——通过标准化的协议适配层接入各类嵌入式硬件，让任何具备传感与执行能力的设备都能获得同样的自主智能。

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

目前已在 **PX4 SITL + Gazebo Harmonic** 仿真环境中构建验证平台：

<p align="center">
  <img src="assets/gazebo_demo.gif" alt="Gazebo 仿真" width="720" />
  <br>
  <em>X500无人机在城市救援场景中的仿真测试（4倍速播放）</em>
</p>

| 组件 | 技术选型 |
|------|----------|
| 飞控系统 | PX4 v1.15 软件在环仿真 |
| 仿真环境 | Gazebo Harmonic (gz sim 8.x) |
| 传感器模型 | 5路摄像头 + 3D LiDAR (360°×16层) |
| 通信协议 | Micro XRCE-DDS + MAVSDK gRPC |
| 坐标系 | NED (北-东-地) 局部坐标系 |

**仿真场景要素**：倒塌建筑、被困人员模型、火灾烟雾效果、障碍物布置、地面标记等。

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
├── server.py                    # 服务入口
├── config.py                    # 全局配置（从 .env 读取）
├── llm_client.py                # LLM 多 Provider 客户端
├── .env.example                 # 环境变量模板
├── requirements.txt             # Python 依赖
│
├── brain/                       # 决策核心
│   ├── agent_loop.py            #   自主决策循环
│   ├── planner_agent.py         #   LLM 任务规划器
│   └── chat_mode.py             #   对话模式
│
├── perception/                  # 感知系统
│   ├── daemon.py                #   被动感知守护线程
│   ├── vlm_analyzer.py          #   主动视觉分析（VLM）
│   ├── prompts.py               #   感知提示词
│   └── gz_camera.py             #   Gazebo 摄像头桥接
│
├── skills/                      # 技能库
│   ├── hard_skills.py           #   硬技能实现
│   ├── soft_skills.py           #   软技能执行器
│   ├── docs/                    #   硬技能文档（13 个）
│   ├── soft_docs/               #   软技能策略文档（3 个）
│   └── dynamic_skill_gen.py     #   动态技能生成
│
├── memory/                      # 记忆与学习
│   ├── reflection_engine.py     #   反思引擎
│   ├── skill_evolution.py       #   技能进化
│   ├── world_model.py           #   世界模型
│   └── task_log.py              #   任务日志
│
├── robot_profile/               # 身份文档
│   ├── SOUL.md / BODY.md        #   人格与硬件描述
│   ├── MEMORY.md / SKILLS.md    #   经验与技能自述
│   └── WORLD_MAP.md             #   环境地图
│
├── adapters/                    # 硬件适配层
│   ├── base_adapter.py          #   抽象接口
│   ├── px4_adapter.py           #   PX4 适配器
│   ├── sim_adapter.py           #   仿真适配器
│   └── mock_adapter.py          #   Mock 测试适配器
│
├── sim/                         # 仿真资源
│   ├── models/x500_sensor/      #   自定义无人机模型（5 摄像头 + LiDAR）
│   ├── worlds/urban_rescue.sdf  #   自定义 Gazebo 场景
│   ├── airframes/               #   自定义 airframe
│   └── px4_patches.diff         #   PX4 定制补丁
│
├── ui/                          # Web 监控界面（React）
│   └── src/components/          #   9 个 React 组件
│
├── scripts/                     # 脚本
│   ├── setup_px4.sh             #   一键安装 PX4 + 打补丁
│   └── start_gz_sim.sh          #   一键启动仿真
│
├── docs/                        # 开发文档
│   ├── ARCHITECTURE.md          #   系统架构
│   ├── SIMULATION_SETUP.md      #   仿真环境搭建
│   ├── ADAPTER_GUIDE.md         #   适配器接入指南
│   ├── SKILL_GUIDE.md           #   技能开发指南
│   ├── PERCEPTION_GUIDE.md      #   感知模块接入指南
│   └── LLM_CONFIG.md            #   LLM 配置说明
│
└── assets/                      # 图片与演示资源
```

## 研究进展与计划

### 已实现
- [x] 自主决策循环 · 身份与状态管理 · 12 项硬技能 + 3 项软技能
- [x] 被动 + 主动双层感知 · 经验积累与反思 · 动态技能生成
- [x] PX4 + Gazebo 仿真集成 · Web 监控与交互界面

### 未来方向
- [ ] 真实无人机移植 · ROS2 集成 · Sim2Real 迁移
- [ ] 多智能体协作 · 通用设备框架解耦 · 安全决策边界

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