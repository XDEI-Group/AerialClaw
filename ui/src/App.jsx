/**
 * App.jsx — AerialClaw v2.0 控制台主界面 (精简版)
 *
 * 布局：
 *   ┌──────────────────────────────────────────────────────┐
 *   │  Header: Logo | 连接 | 初始化 | 模式 | Tab 导航        │
 *   ├──────────────────────────────────────────────────────┤
 *   │  Tab 内容区                                           │
 *   │   控制台 → RobotPanel + SkillPanel/AiMonitor          │
 *   │   技能   → SkillEvolutionPanel                        │
 *   └──────────────────────────────────────────────────────┘
 */
import { useState, useEffect } from 'react'
import { useSocket } from './hooks/useSocket'
import Header from './components/Header'
import RobotPanel from './components/RobotPanel'
import SkillPanel from './components/SkillPanel'
import LogPanel from './components/LogPanel'
import SensorPanel from './components/SensorPanel'
import AiMonitorPanel from './components/AiMonitorPanel'
import ModelConfig from './components/ModelConfig'
import CockpitView from './components/CockpitView'
import SkillEvolutionPanel from './components/SkillEvolutionPanel'
import './App.css'

const TABS = [
  { key: 'console',  label: '控制台',  icon: '🖥' },
  { key: 'skill',    label: '技能进化', icon: '🧩' },
]

function TabBar({ activeTab, onTabChange }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 2,
      padding: '0 8px',
      background: 'var(--bg-panel)',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {TABS.map(tab => {
        const active = activeTab === tab.key
        return (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '8px 14px',
              background: 'none',
              border: 'none',
              borderBottom: active ? '2px solid #00d4ff' : '2px solid transparent',
              color: active ? '#00d4ff' : '#64748b',
              fontSize: 12, fontWeight: active ? 700 : 400,
              cursor: 'pointer',
              transition: 'color .15s',
              marginBottom: -1,
            }}
          >
            <span style={{ fontSize: 13 }}>{tab.icon}</span>
            {tab.label}
          </button>
        )
      })}
    </div>
  )
}

export default function App() {
  const {
    connected, systemStatus, worldState, skillCatalog, logs,
    lastSkillResult, lastAiPlan, lastAiReport,
    sensorCamera, sensorCameras, sensorLidar,
    cockpitOpen,
    cockpitInitialView,
    chatHistory,
    aiThinking,
    aiThoughts,
    aiStream,
    executeSkill, selectRobot, setMode, submitAiTask, stopExecution, initSystem,
    openCockpit, closeCockpit, getSocket,
    sendChat,
  } = useSocket()

  const [activeTab,       setActiveTab]       = useState('console')
  const [aiReportVisible, setAiReportVisible] = useState(false)
  const [showModelConfig, setShowModelConfig] = useState(false)

  useEffect(() => {
    if (lastAiReport) setAiReportVisible(true)
  }, [lastAiReport])

  const handleModeSwitch = (mode) => {
    setMode(mode)
    if (mode === 'manual') setAiReportVisible(false)
  }

  const handleSubmitAiTask = (task, useTools) => {
    setAiReportVisible(false)
    submitAiTask(task, useTools)
  }

  const socket = getSocket()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>

      {/* 驾驶舱全屏视图 */}
      {cockpitOpen && (
        <CockpitView
          socket={socket}
          sensorCameras={sensorCameras}
          sensorLidar={sensorLidar}
          onClose={closeCockpit}
          initialView={cockpitInitialView}
        />
      )}

      {/* 顶部状态栏 */}
      <Header
        connected={connected}
        systemStatus={systemStatus}
        onInit={initSystem}
        onModeSwitch={handleModeSwitch}
        onStop={stopExecution}
      />

      {/* Tab 导航栏 */}
      <TabBar activeTab={activeTab} onTabChange={setActiveTab} />

      {/* ── 控制台 Tab ────────────────────────────────────────────────────────── */}
      {activeTab === 'console' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
          <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>

            {/* 左侧：机器人状态 */}
            <div style={{
              width: 220, flexShrink: 0,
              borderRight: '1px solid var(--border)',
              padding: 10, overflow: 'hidden',
              background: 'var(--bg-panel)',
            }}>
              <RobotPanel
                worldState={worldState}
                currentRobot={systemStatus.current_robot}
                onSelectRobot={selectRobot}
              />
            </div>

            {/* 中间：技能控制 / AI 监控 */}
            <div style={{
              flex: 1, borderRight: '1px solid var(--border)',
              padding: 10, overflow: 'hidden',
              background: 'var(--bg)', position: 'relative',
            }}>
              {systemStatus.mode === 'manual' ? (
                <SkillPanel
                  skillCatalog={skillCatalog}
                  currentRobot={systemStatus.current_robot}
                  worldState={worldState}
                  isExecuting={systemStatus.is_executing}
                  onExecuteSkill={executeSkill}
                  lastResult={lastSkillResult}
                />
              ) : (
                <AiMonitorPanel
                  sensorCameras={sensorCameras}
                  sensorLidar={sensorLidar}
                  aiThinking={aiThinking}
                  aiThoughts={aiThoughts}
                  aiStream={aiStream}
                  lastAiPlan={lastAiPlan}
                  logs={logs}
                  onOpenCockpit={openCockpit}
                  socket={socket}
                  worldState={worldState}
                  onMapCommand={(cmd) => sendChat(cmd)}
                />
              )}
            </div>

            {/* 右侧：传感器 + 模型配置 + AI 面板 */}
            <div style={{
              width: 320, flexShrink: 0,
              display: 'flex', flexDirection: 'column',
              overflow: 'hidden', borderLeft: '1px solid var(--border)',
            }}>
              {systemStatus.mode === 'manual' && (
                <div style={{
                  height: 200, flexShrink: 0,
                  padding: 10, overflow: 'auto',
                  background: 'var(--bg-panel)',
                  borderBottom: '1px solid var(--border)',
                }}>
                  <SensorPanel
                    sensorCamera={sensorCamera}
                    sensorCameras={sensorCameras}
                    sensorLidar={sensorLidar}
                    onOpenCockpit={openCockpit}
                  />
                </div>
              )}
              {/* 模型配置（可折叠） */}
              <div style={{ flexShrink: 0, borderBottom: '1px solid var(--border)' }}>
                <div
                  onClick={() => setShowModelConfig(!showModelConfig)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '6px 10px',
                    cursor: 'pointer',
                    background: 'var(--bg-panel)',
                    userSelect: 'none',
                  }}
                >
                  <span style={{ fontSize: 12 }}>⚙️</span>
                  <span style={{ fontSize: 11, color: 'var(--text-dim)', fontWeight: 600 }}>模型配置</span>
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)' }}>
                    {showModelConfig ? '▾' : '▸'}
                  </span>
                </div>
                {showModelConfig && (
                  <div style={{
                    padding: '0 10px 10px',
                    maxHeight: 360, overflowY: 'auto',
                    background: 'var(--bg-panel)',
                  }}>
                    <ModelConfig />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 底部：实时日志 */}
          <div style={{ height: 180, flexShrink: 0, borderTop: '1px solid var(--border)' }}>
            <LogPanel logs={logs} />
          </div>
        </div>
      )}

      {/* ── 技能进化 Tab ──────────────────────────────────────────────────────── */}
      {activeTab === 'skill' && (
        <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
          <SkillEvolutionPanel socket={socket} connected={connected} />
        </div>
      )}

    </div>
  )
}
