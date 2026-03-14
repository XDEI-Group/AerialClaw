/**
 * App.jsx — AerialClaw 控制台主界面
 *
 * 布局：
 *   ┌──────────────────────────────────────────────┐
 *   │  Header: Logo | 连接状态 | 初始化 | 模式切换   │
 *   ├──────────┬─────────────────┬─────────────────┤
 *   │          │                 │                 │
 *   │ 机器人   │  技能控制        │  AI / 执行报告  │
 *   │ 状态面板  │  (手动模式)      │  (AI 模式)      │
 *   │          │                 │                 │
 *   ├──────────┴─────────────────┴─────────────────┤
 *   │  实时执行日志 (所有模式可见)                    │
 *   └──────────────────────────────────────────────┘
 */
import { useState, useEffect } from 'react'
import { useSocket } from './hooks/useSocket'
import Header from './components/Header'
import RobotPanel from './components/RobotPanel'
import SkillPanel from './components/SkillPanel'
import AiPanel from './components/AiPanel'
import LogPanel from './components/LogPanel'
import SensorPanel from './components/SensorPanel'
import AiMonitorPanel from './components/AiMonitorPanel'
import ModelConfig from './components/ModelConfig'
import CockpitView from './components/CockpitView'
import './App.css'

export default function App() {
  const {
    connected, systemStatus, worldState, skillCatalog, logs,
    lastSkillResult, lastAiPlan, lastAiReport,
    sensorCamera, sensorCameras, sensorLidar,
    cockpitOpen,
    cockpitInitialView,
    chatHistory,
    aiThinking,
    aiStream,
    executeSkill, selectRobot, setMode, submitAiTask, stopExecution, initSystem,
    openCockpit, closeCockpit, getSocket,
    sendChat,
  } = useSocket()

  // AI 报告只在有新报告时显示，切换任务时清空
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>

      {/* 驾驶舱全屏视图 */}
      {cockpitOpen && (
        <CockpitView
          socket={getSocket()}
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

      {/* 主内容区 */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden', minHeight: 0 }}>

        {/* 左侧：机器人状态 */}
        <div style={{
          width: 220,
          flexShrink: 0,
          borderRight: '1px solid var(--border)',
          padding: 10,
          overflow: 'hidden',
          background: 'var(--bg-panel)',
        }}>
          <RobotPanel
            worldState={worldState}
            currentRobot={systemStatus.current_robot}
            onSelectRobot={selectRobot}
          />
        </div>

        {/* 中间：技能控制（手动模式）/ 占位（AI 模式） */}
        <div style={{
          flex: 1,
          borderRight: '1px solid var(--border)',
          padding: 10,
          overflow: 'hidden',
          background: 'var(--bg)',
          position: 'relative',
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
              aiStream={aiStream}
              lastAiPlan={lastAiPlan}
              logs={logs}
              onOpenCockpit={openCockpit}
            />
          )}
        </div>

        {/* 右侧：传感器（手动模式） + AI 面板 */}
        <div style={{
          width: 320,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          borderLeft: '1px solid var(--border)',
        }}>
          {/* 传感器面板 — 仅手动模式显示（AI 模式下传感器在中间面板） */}
          {systemStatus.mode === 'manual' && (
            <div style={{
              height: 200,
              flexShrink: 0,
              padding: 10,
              overflow: 'auto',
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
          {/* 模型配置面板 (可折叠) */}
          <div style={{
            flexShrink: 0,
            borderBottom: '1px solid var(--border)',
          }}>
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
                maxHeight: 360,
                overflowY: 'auto',
                background: 'var(--bg-panel)',
              }}>
                <ModelConfig />
              </div>
            )}
          </div>
          {/* AI 面板 */}
          <div style={{
            flex: 1,
            minHeight: 0,
            padding: 10,
            overflow: 'hidden',
            background: 'var(--bg-panel)',
          }}>
            <AiPanel
              mode={systemStatus.mode}
              isExecuting={systemStatus.is_executing}
              lastAiPlan={lastAiPlan}
              lastAiReport={aiReportVisible ? lastAiReport : null}
              onSubmitTask={handleSubmitAiTask}
              onStop={stopExecution}
              chatHistory={chatHistory}
              onSendChat={sendChat}
            />
          </div>
        </div>
      </div>

      {/* 底部：实时日志 */}
      <div style={{
        height: 180,
        flexShrink: 0,
        borderTop: '1px solid var(--border)',
      }}>
        <LogPanel logs={logs} />
      </div>
    </div>
  )
}
