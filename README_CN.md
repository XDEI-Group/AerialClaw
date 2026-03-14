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

项目由西安电子科技大学计算机科学与技术学院 ROBOTY 实验室开发，基于 [OpenClaw](https://github.com/openclaw/openclaw) 的设计理念，通过 Markdown 文档定义和维护智能体的认知状态与能力边界，由模型自主读写更新，实现真正的"个性化"——每架无人机都拥有属于自己的经验、偏好与成长轨迹。

> *"不预设流程，只定义能力——让每架无人机在任务中自主思考、积累经验、持续成长。"*

<p align="center">
  <img src="assets/demo.gif" alt="AerialClaw 演示" width="720" />
</p>

---

## 研究背景与动机

当前无人机系统大多采用预编程或远程遥控方式运行，需要针对特定场景编写控制脚本，缺乏对未知环境的适应能力和任务经验的积累机制。

AerialClaw 尝试探索一种不同的技术路径：**通过LLM赋予无人机自主环境理解与决策能力**。

- 🧠 **推理而非仅执行** — LLM 模型解析任务目标，生成分步决策序列
- 👁️ **语义级环境理解** — 将多源传感器数据转换为自然语言描述，支持基于常识的推理
- 📝 **飞行经验自积累** — 建立任务记忆库，支持基于历史经验的决策优化
- 🪪 **能力边界自感知** — 维护系统性能档案，记录能力边界与历史表现

| | 传统无人机 | AerialClaw 无人机 |
|:---|:---|:---|
| **任务描述** | "执行航点列表" | "去这片区域搜索幸存者" |
| **失败处理** | 悬停或坠机 | 分析原因，切换策略重试 |
| **新任务** | 重写代码 | 一段自然语言指令 |
| **经验利用** | 每次飞行都从零开始 | 每次飞行都在积累经验 |

## 系统架构设计

<p align="center">
  <img src="assets/architecture.png" alt="AerialClaw 系统架构" width="900" />
</p>

### 从OpenClaw到AerialClaw：研究思路演进

[OpenClaw](https://github.com/openclaw/openclaw) 项目验证了身份文档与记忆反思机制在对话智能体中的有效性。AerialClaw 在此基础上进一步探索：**该框架能否应用于具有物理约束的自主移动平台？**

| 维度 | OpenClaw (对话智能体) | AerialClaw (自主无人机) |
|---|---|---|
| 身份定义 | SOUL.md → 对话风格 | SOUL.md → 飞行策略偏好 |
| 记忆系统 | 对话历史记录 | MEMORY.md → 任务经验库 |
| 技能实现 | API调用与文本处理 | 物理动作执行与环境交互 |
| 交互模式 | 响应用户输入 | 自主感知-决策循环 |
| 学习机制 | 从对话中学习 | 从飞行经验中学习 |

### 核心设计原则

1. **第一人称决策视角** — 系统以无人机为主体视角进行决策表述
2. **语义级传感器融合** — 将原始传感器数据转换为LLM可理解的语义描述
3. **文档驱动技能定义** — 飞行动作与策略以可读文档形式存储，支持动态加载
4. **分层记忆管理机制** — 实现长期经验积累与短期上下文的高效平衡

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
- [PX4 Autopilot](https://docs.px4.io/main/en/dev_setup/building_px4.html) v1.15+
- [Gazebo Harmonic](https://gazebosim.org/docs/harmonic/install)
- [Micro XRCE-DDS Agent](https://github.com/eProsima/Micro-XRCE-DDS-Agent)
- MAVSDK-Python (`pip install mavsdk`)

### 安装步骤

```bash
# 克隆代码仓库
git clone https://github.com/XDEI-Group/AerialClaw.git
cd AerialClaw

# 配置Python环境
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 构建Web界面
cd ui
npm install
npm run build
cd ..
```

### LLM服务配置

修改 `config.py` 配置文件：

```python
ACTIVE_PROVIDER = "ollama_local"   # 本地模型服务
# ACTIVE_PROVIDER = "openai"       # OpenAI兼容API
MODULE_CONFIG["vlm"]["provider"] = "gpt4o_vlm"  # 视觉理解模型
```

## 快速开始

```bash
# 启动仿真环境
./scripts/start_gz_sim.sh urban_rescue

# 启动MAVSDK服务
mavsdk_server -p 50051 udp://:14540

# 启动AerialClaw主服务
python server.py

# 访问Web界面
# http://localhost:8000
```

通过自然语言指令测试系统功能：
- *"起飞至15米高度并进行环境观察"*
- *"搜索区域内的异常情况"*
- *"报告当前电量状态"*

## 项目结构

```
AerialClaw/
├── brain/                    # 决策核心模块
├── perception/               # 感知处理模块
├── skills/                   # 技能库
│   ├── hard_skills.py        # 基础动作实现
│   ├── docs/                 # 技能文档
│   └── soft_docs/            # 场景策略文档
├── memory/                   # 记忆与学习模块
├── robot_profile/            # 状态配置文件
├── adapters/                 # 硬件适配层
├── sim/                      # 仿真接口
├── ui/                       # Web界面
├── server.py                 # 服务入口
└── config.py                 # 配置文件
```

## 研究进展与计划

### 已实现功能
- [x] 自主决策循环框架
- [x] 身份与状态管理系统
- [x] 基础飞行动作技能库
- [x] 多传感器语义融合接口
- [x] 经验积累与反思机制
- [x] PX4+Gazebo仿真集成
- [x] Web监控与交互界面

### 当前工作重点
- [ ] 复杂场景下的性能评估
- [ ] 长期自主任务的稳定性测试
- [ ] 决策效能的量化分析

### 未来研究方向
- [ ] 真实无人机平台的移植验证
- [ ] ROS2框架的集成方案
- [ ] 仿真到现实的迁移学习
- [ ] 多智能体协作机制探索
- [ ] 通用设备框架解耦 — 标准化协议适配，支持接入多种嵌入式设备
- [ ] 安全决策边界 — LLM 输出的动作合规校验、地理围栏与飞行包线约束

## 参与贡献

欢迎相关领域研究者参与：
- **场景与任务设计** — 扩展测试场景与评估任务
- **感知算法改进** — 优化传感器数据处理与融合
- **平台适配扩展** — 支持更多无人机硬件平台
- **评估基准建立** — 设计科学的性能评估体系

## 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。

## 致谢

AerialClaw 的研究思路受到 [OpenClaw](https://github.com/openclaw/openclaw) 项目的启发，在此表示感谢。

项目基于以下开源技术构建：
[PX4](https://px4.io/) · [Gazebo](https://gazebosim.org/) · [MAVSDK](https://mavsdk.mavlink.io/) · [React](https://react.dev/) · [Vite](https://vitejs.dev/)

---

*本项目为学术研究性质的开源项目，旨在探索LLM在自主移动平台中的应用潜力。*