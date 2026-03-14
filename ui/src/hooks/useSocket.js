/**
 * useSocket.js
 * Socket.IO 连接 Hook，统一管理 WebSocket 事件
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { io } from 'socket.io-client'

const SERVER_URL = window.location.protocol + '//' + window.location.hostname + ':5001'

export function useSocket() {
  const socketRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const [systemStatus, setSystemStatus] = useState({
    initialized: false,
    mode: 'manual',
    is_executing: false,
    current_robot: 'UAV_1',
  })
  const [worldState, setWorldState] = useState({ robots: {}, targets: [] })
  // skillCatalog: { robot_id: [skills] } — 每台机器人独立的技能表，执行历史互不干扰
  const [skillCatalog, setSkillCatalog] = useState({})
  const [logs, setLogs] = useState([])
  const [lastSkillResult, setLastSkillResult] = useState(null)
  const [lastAiPlan, setLastAiPlan] = useState(null)
  const [lastAiReport, setLastAiReport] = useState(null)
  const [aiThinking, setAiThinking] = useState({ phase: 'idle', detail: '' })
  const [aiStream, setAiStream] = useState({ text: '', done: true })
  const [sensorCamera, setSensorCamera] = useState(null)
  const [sensorCameras, setSensorCameras] = useState({})
  const [sensorLidar, setSensorLidar] = useState(null)
  const [cockpitOpen, setCockpitOpen] = useState(false)
  const [cockpitInitialView, setCockpitInitialView] = useState('front')
  const [chatHistory, setChatHistory] = useState([])

  useEffect(() => {
    const socket = io(SERVER_URL, {
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
    })
    socketRef.current = socket

    socket.on('connect', () => {
      setConnected(true)
      console.log('[Socket] connected:', socket.id)
    })
    socket.on('disconnect', () => {
      setConnected(false)
      console.log('[Socket] disconnected')
    })

    socket.on('system_status', (data) => setSystemStatus(data))
    socket.on('world_state', (data) => setWorldState(data))
    socket.on('skill_catalog', (data) => setSkillCatalog(data))
    socket.on('skill_result', (data) => setLastSkillResult(data))
    socket.on('ai_plan_result', (data) => setLastAiPlan(data))
    socket.on('ai_execution_report', (data) => setLastAiReport(data))
    socket.on('ai_thinking', (data) => setAiThinking(data))
    socket.on('ai_stream', (data) => setAiStream(prev => {
      if (data.done) return { text: '', done: true }
      return { text: (prev.done ? '' : (prev.text || '')) + data.token, done: false }
    }))
    socket.on('sensor_camera', (data) => setSensorCamera(data))
    socket.on('sensor_cameras', (data) => setSensorCameras(data))
    socket.on('sensor_lidar', (data) => setSensorLidar(data))
    socket.on('ai_chat_reply', (data) => {
      if (data.ok && data.reply) {
        setChatHistory(prev => [
          ...prev,
          { role: 'assistant', content: data.reply, intent: data.intent },
        ])
      }
    })

    // 新机器人动态加入：world_state 已包含完整信息，这里只做自动切换逻辑
    socket.on('robot_joined', (info) => {
      console.log('[Socket] robot_joined:', info)
      // 如果当前没有选中机器人（或选中的是默认占位），自动切换到新机器人
      setSystemStatus(prev => {
        if (!prev.current_robot || prev.current_robot === '') {
          return { ...prev, current_robot: info.robot_id }
        }
        return prev
      })
    })

    socket.on('log', (entry) => {
      setLogs(prev => {
        const next = [...prev, entry]
        return next.length > 300 ? next.slice(-300) : next
      })
    })

    return () => {
      socket.disconnect()
    }
  }, [])

  // 执行技能（手动模式）
  const executeSkill = useCallback((robotId, skillName, parameters = {}) => {
    if (socketRef.current) {
      socketRef.current.emit('execute_skill', { robot_id: robotId, skill_name: skillName, parameters })
    }
  }, [])

  // 选择机器人
  const selectRobot = useCallback((robotId) => {
    if (socketRef.current) {
      socketRef.current.emit('select_robot', { robot_id: robotId })
    }
  }, [])

  // 切换模式
  const setMode = useCallback((mode) => {
    if (socketRef.current) {
      socketRef.current.emit('set_mode', { mode })
    }
    // 也通过 REST API 切换（更可靠）
    fetch(`${SERVER_URL}/api/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    })
      .then(r => r.json())
      .then(data => console.log('[Mode]', data))
      .catch(e => console.error('[Mode error]', e))
  }, [])

  // 提交 AI 任务
  const submitAiTask = useCallback((task, useTools = false) => {
    if (socketRef.current) {
      setAiStream({ text: '', done: true }) // 重置流
      socketRef.current.emit('ai_task', { task, use_tools: useTools })
    }
  }, [])

  // 停止执行
  const stopExecution = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.emit('stop_execution')
    }
  }, [])

  // 初始化系统
  const initSystem = useCallback(() => {
    fetch(`${SERVER_URL}/api/init`, { method: 'POST' })
      .then(r => r.json())
      .then(d => console.log('[Init]', d))
      .catch(e => console.error('[Init error]', e))
  }, [])

  // 打开/关闭驾驶舱
  const openCockpit = useCallback((view) => { setCockpitInitialView(view || 'front'); setCockpitOpen(true) }, [])
  const closeCockpit = useCallback(() => setCockpitOpen(false), [])

  // AI 对话
  const sendChat = useCallback((message) => {
    if (socketRef.current) {
      // 先立即加用户消息到历史
      setChatHistory(prev => [...prev, { role: 'user', content: message }])
      socketRef.current.emit('ai_chat', { message })
    }
  }, [])
  // 获取原始 socket 引用 (驾驶舱需要)
  const getSocket = useCallback(() => socketRef.current, [])

  return {
    connected,
    systemStatus,
    worldState,
    skillCatalog,
    logs,
    lastSkillResult,
    lastAiPlan,
    lastAiReport,
    aiThinking,
    aiStream,
    sensorCamera,
    sensorCameras,
    sensorLidar,
    cockpitOpen,
    cockpitInitialView,
    chatHistory,
    executeSkill,
    selectRobot,
    setMode,
    submitAiTask,
    stopExecution,
    initSystem,
    openCockpit,
    closeCockpit,
    getSocket,
    sendChat,
  }
}
