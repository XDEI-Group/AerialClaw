/**
 * AiMonitorPanel.jsx — AI 模式中间监控面板
 *
 * 上栏: 4 摄像头 (2×2) + LiDAR 雷达图
 * 下栏: 三栏活动面板 (LLM输出 | 规划步骤 | 系统日志)
 */
import { useRef, useEffect, useState } from 'react'
import MapView from './MapView'

/* ── LiDAR 极坐标雷达图 ──────────────────────────────────── */
function LidarRadar({ lidarData, size = 140 }) {
  const canvasRef = useRef(null)
  useEffect(() => {
    const cvs = canvasRef.current
    if (!cvs) return
    const ctx = cvs.getContext('2d')
    const cx = size / 2, cy = size / 2, R = size / 2 - 8
    ctx.clearRect(0, 0, size, size)
    ctx.fillStyle = '#0a0e14'; ctx.fillRect(0, 0, size, size)
    // 距离环
    for (let r = R / 4; r <= R; r += R / 4) {
      ctx.strokeStyle = r === R ? 'rgba(34,197,94,0.25)' : 'rgba(34,197,94,0.08)'
      ctx.lineWidth = 0.5; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke()
    }
    // 方位线
    for (let a = 0; a < Math.PI * 2; a += Math.PI / 4) {
      ctx.strokeStyle = 'rgba(34,197,94,0.08)'; ctx.beginPath()
      ctx.moveTo(cx, cy); ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R); ctx.stroke()
    }

    const is3d = lidarData?.is_3d
    const hasData = is3d ? lidarData?.layers?.length : lidarData?.ranges?.length

    if (!hasData) {
      ctx.fillStyle = 'rgba(34,197,94,0.3)'; ctx.font = '9px monospace'; ctx.textAlign = 'center'
      ctx.fillText('OFFLINE', cx, cy); return
    }

    const { angle_min, angle_max, range_max } = lidarData

    if (is3d && lidarData.layers) {
      // 3D 点云: 多层渲染，颜色从蓝(低)→绿(中)→红(高)
      const layers = lidarData.layers
      const vCount = layers.length
      const hCount = layers[0]?.length || 0
      const step = (angle_max - angle_min) / hCount
      ctx.shadowBlur = 2

      // 高度层颜色: 底层蓝→中间绿→顶层橙红
      const layerColors = layers.map((_, vi) => {
        const t = vCount <= 1 ? 0.5 : vi / (vCount - 1)
        const r = Math.round(34 + t * 200)
        const g = Math.round(197 - t * 100)
        const b = Math.round(94 - t * 60)
        return `rgb(${r},${g},${b})`
      })

      // 从底层往上画，上层覆盖下层
      for (let vi = 0; vi < vCount; vi++) {
        const layer = layers[vi]
        ctx.fillStyle = layerColors[vi]
        ctx.shadowColor = layerColors[vi]
        const ptSize = vi === Math.floor(vCount / 2) ? 2 : 1.5
        for (let hi = 0; hi < layer.length; hi++) {
          const r = layer[hi]
          if (r <= 0 || r >= range_max) continue
          const a = angle_min + step * hi - Math.PI / 2
          const d = (r / range_max) * R
          ctx.fillRect(cx + Math.cos(a) * d - ptSize/2, cy + Math.sin(a) * d - ptSize/2, ptSize, ptSize)
        }
      }
      ctx.shadowBlur = 0

      // 3D 标记
      ctx.fillStyle = 'rgba(34,197,94,0.4)'; ctx.font = '7px monospace'; ctx.textAlign = 'right'
      ctx.fillText(`3D ${vCount}L`, size - 4, size - 4)
    } else {
      // 2D 兼容
      const { ranges } = lidarData
      const step = (angle_max - angle_min) / ranges.length
      ctx.shadowColor = '#22c55e'; ctx.shadowBlur = 3; ctx.fillStyle = '#22c55e'
      for (let i = 0; i < ranges.length; i++) {
        const r = ranges[i]; if (r <= 0 || r > range_max) continue
        const a = angle_min + step * i - Math.PI / 2, d = (r / range_max) * R
        ctx.fillRect(cx + Math.cos(a) * d - 1, cy + Math.sin(a) * d - 1, 2, 2)
      }
      ctx.shadowBlur = 0
    }

    // 无人机标记
    ctx.fillStyle = '#22c55e'; ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.fill()
    ctx.fillStyle = 'rgba(34,197,94,0.6)'; ctx.beginPath()
    ctx.moveTo(cx, cy - 7); ctx.lineTo(cx - 3, cy - 2); ctx.lineTo(cx + 3, cy - 2); ctx.fill()
  }, [lidarData, size])
  return <canvas ref={canvasRef} width={size} height={size} style={{ borderRadius: 4 }} />
}

/* ── 摄像头 ──────────────────────────────────────────────── */
function CameraView({ src, label }) {
  return (
    <div style={{ position: 'relative', background: '#0a0e14', borderRadius: 3, overflow: 'hidden',
      border: '1px solid rgba(34,197,94,0.15)' }}>
      {src ? (
        <img src={`data:image/jpeg;base64,${src}`} alt={label}
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', opacity: 0.9 }} />
      ) : (
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'rgba(34,197,94,0.3)', fontSize: 9, fontFamily: 'monospace' }}>NO SIGNAL</div>
      )}
      <span style={{ position: 'absolute', top: 2, left: 4, fontSize: 8, color: '#22c55e',
        fontFamily: 'monospace', textShadow: '0 0 4px rgba(34,197,94,0.5)', letterSpacing: 1 }}>{label}</span>
      <div style={{ position: 'absolute', inset: 0,
        background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)',
        pointerEvents: 'none' }} />
    </div>
  )
}

/* ── 栏标题 ──────────────────────────────────────────────── */
function ColHeader({ icon, title, status, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '3px 6px',
      borderBottom: '1px solid rgba(34,197,94,0.1)', fontSize: 9, letterSpacing: 1.5,
      color: 'rgba(34,197,94,0.5)', fontFamily: 'monospace', flexShrink: 0 }}>
      <span>{icon}</span><span>{title}</span>
      {status && (
        <span style={{ marginLeft: 'auto', fontSize: 8, color: color || '#22c55e', display: 'flex', alignItems: 'center', gap: 3 }}>
          <span style={{ width: 5, height: 5, borderRadius: '50%', background: color || '#22c55e',
            boxShadow: `0 0 4px ${color || '#22c55e'}`, animation: 'pulse 2s infinite' }} />
          {status}
        </span>
      )}
    </div>
  )
}

/* ── 栏1: LLM 流式输出 ──────────────────────────────────── */
function LLMColumn({ aiStream, aiThinking }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [aiStream])

  const phase = aiThinking?.phase || 'idle'
  const isActive = phase === 'planning' || (aiStream?.text && !aiStream?.done)
  const statusText = phase === 'planning' ? 'THINKING' : !aiStream?.done ? 'STREAMING' : 'IDLE'
  const statusColor = isActive ? '#a78bfa' : '#4a5568'

  const raw = aiStream?.text || ''
  const displayText = raw.replace(/<think>[\s\S]*?<\/think>/gi, '').trim()
  const thinkMatch = raw.match(/<think>([\s\S]*?)(<\/think>|$)/i)
  const thinkText = thinkMatch ? thinkMatch[1].trim() : ''

  return (
    <div style={{ flex: 1.2, display: 'flex', flexDirection: 'column', minWidth: 0,
      background: '#0a0e14', borderRadius: 4, border: '1px solid rgba(167,139,250,0.15)', overflow: 'hidden' }}>
      <ColHeader icon="▸" title="LLM OUTPUT" status={statusText} color={statusColor} />
      <div ref={ref} style={{ flex: 1, overflowY: 'auto', padding: '4px 6px',
        fontFamily: '"JetBrains Mono", "Fira Code", monospace', fontSize: 10, lineHeight: 1.6 }}>
        {thinkText && (
          <div style={{ color: 'rgba(167,139,250,0.4)', borderLeft: '2px solid rgba(167,139,250,0.2)',
            paddingLeft: 6, marginBottom: 4, fontSize: 9 }}>
            <div style={{ color: 'rgba(167,139,250,0.6)', fontSize: 8, marginBottom: 2 }}>// reasoning chain</div>
            {thinkText.slice(-400)}
          </div>
        )}
        {displayText ? (
          <span style={{ color: '#e2e8f0' }}>
            {displayText}
            {!aiStream?.done && <span className="cursor-blink">▊</span>}
          </span>
        ) : (
          <span style={{ color: 'rgba(167,139,250,0.2)' }}>{'>'} Awaiting LLM response..._</span>
        )}
      </div>
    </div>
  )
}

/* ── 栏2: 执行步骤 (实时从 aiThinking 事件累积) ──────────── */
function PlanColumn({ aiThinking, lastAiPlan, logs }) {
  const [steps, setSteps] = useState([])
  const ref = useRef(null)

  // 从 aiThinking 事件中累积步骤
  useEffect(() => {
    if (aiThinking?.action?.skill && aiThinking?.iteration) {
      setSteps(prev => {
        const existing = prev.find(s => s.iteration === aiThinking.iteration)
        if (existing) return prev
        return [...prev, {
          iteration: aiThinking.iteration,
          skill: aiThinking.action.skill,
          params: aiThinking.action.parameters || {},
          decision: aiThinking.decision,
          status: 'running',
        }]
      })
    }
    if (aiThinking?.phase === 'idle') {
      // 任务结束，标记所有步骤完成
      setSteps(prev => prev.map(s => ({ ...s, status: 'done' })))
    }
  }, [aiThinking])

  // 从系统日志中更新步骤状态
  useEffect(() => {
    if (!logs?.length) return
    const last = logs[logs.length - 1]
    const msg = typeof last === 'object' ? (last.message || last.msg || '') : String(last)
    if (msg.includes('✅') || msg.includes('❌')) {
      setSteps(prev => {
        const updated = [...prev]
        const running = updated.findLast(s => s.status === 'running')
        if (running) {
          running.status = msg.includes('✅') ? 'done' : 'failed'
        }
        return updated
      })
    }
    // 新任务开始时清空
    if (msg.includes('启动 Agent') || msg.includes('启动自主')) {
      setSteps([])
    }
  }, [logs])

  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [steps])

  const phase = aiThinking?.phase || 'idle'
  const runningCount = steps.filter(s => s.status === 'running').length
  const doneCount = steps.filter(s => s.status === 'done').length
  const statusText = runningCount > 0 ? `STEP ${steps.length}` : steps.length > 0 ? `${doneCount}/${steps.length} DONE` : 'IDLE'
  const statusColor = runningCount > 0 ? '#f59e0b' : doneCount > 0 ? '#22c55e' : '#4a5568'

  return (
    <div style={{ flex: 0.8, display: 'flex', flexDirection: 'column', minWidth: 0,
      background: '#0a0e14', borderRadius: 4, border: '1px solid rgba(34,197,94,0.15)', overflow: 'hidden' }}>
      <ColHeader icon="▸" title="PLAN" status={statusText} color={statusColor} />
      <div ref={ref} style={{ flex: 1, overflowY: 'auto', padding: '4px 6px', fontFamily: 'monospace', fontSize: 10, lineHeight: 1.8 }}>
        {steps.length === 0 && <div style={{ color: 'rgba(34,197,94,0.2)' }}>{'>'} Awaiting actions_</div>}
        {steps.map((s, i) => {
          const icon = s.status === 'done' ? '✓' : s.status === 'failed' ? '✗' : '▸'
          const color = s.status === 'done' ? '#22c55e' : s.status === 'failed' ? '#ef4444' : '#f59e0b'
          const paramStr = Object.entries(s.params || {}).filter(([,v]) => v !== undefined && v !== null && v !== '')
            .map(([k,v]) => `${k}=${typeof v === 'number' ? v : JSON.stringify(v)}`).join(', ')
          return (
            <div key={i} style={{ display: 'flex', gap: 4, color, fontSize: 10 }}>
              <span style={{ flexShrink: 0, width: 10, textAlign: 'center',
                textShadow: s.status === 'running' ? '0 0 6px #f59e0b' : 'none' }}>{icon}</span>
              <span style={{ color: s.status === 'running' ? '#f59e0b' : '#cbd5e1' }}>
                {i + 1}. {s.skill}
                {paramStr && <span style={{ color: '#64748b', fontSize: 9 }}> ({paramStr})</span>}
              </span>
              {s.status === 'running' && <span style={{ marginLeft: 'auto', animation: 'pulse 1s infinite' }}>⏳</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ── 栏3: 系统日志 ──────────────────────────────────────── */
function SysLogColumn({ logs, aiThinking }) {
  const ref = useRef(null)
  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight }, [logs])
  const phase = aiThinking?.phase || 'idle'
  const statusText = phase !== 'idle' ? phase.toUpperCase() : 'IDLE'
  const statusColor = phase === 'reflecting' ? '#60a5fa' : phase !== 'idle' ? '#22c55e' : '#4a5568'
  const recent = (logs || []).slice(-40)

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0,
      background: '#0a0e14', borderRadius: 4, border: '1px solid rgba(96,165,250,0.15)', overflow: 'hidden' }}>
      <ColHeader icon="▸" title="SYSTEM" status={statusText} color={statusColor} />
      <div ref={ref} style={{ flex: 1, overflowY: 'auto', padding: '4px 6px', fontFamily: 'monospace', fontSize: 9.5, lineHeight: 1.6 }}>
        {recent.length === 0 && <div style={{ color: 'rgba(96,165,250,0.2)' }}>{'>'} System ready_</div>}
        {recent.map((log, i) => {
          const lv = typeof log === 'object' ? log.level : 'info'
          const msg = typeof log === 'object' ? (log.message || log.msg || JSON.stringify(log)) : String(log)
          const dotColor = lv === 'error' ? '#ef4444' : lv === 'success' ? '#22c55e' : lv === 'warn' ? '#f59e0b' : '#64748b'
          return (
            <div key={i} style={{ display: 'flex', gap: 4,
              color: i === recent.length - 1 ? '#cbd5e1' : '#64748b',
              opacity: i === recent.length - 1 ? 1 : 0.7 }}>
              <span style={{ color: dotColor, flexShrink: 0 }}>●</span>
              <span>{msg}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ── 摄像头方向配置 ──────────────────────────────────────── */
const CAM_DIRECTIONS = [
  { key: 'front', label: '▲ FRONT', cockpit: 'front' },
  { key: 'left',  label: '◀ LEFT',  cockpit: 'left' },
  { key: 'right', label: '▶ RIGHT', cockpit: 'right' },
  { key: 'rear',  label: '▼ REAR',  cockpit: 'rear' },
  { key: 'down',  label: '⊙ DOWN',  cockpit: 'down' },
]

/* ── 主面板 ──────────────────────────────────────────────── */
export default function AiMonitorPanel({
  sensorCameras, sensorLidar, aiThinking, aiStream, lastAiPlan, logs, onOpenCockpit,
  socket, worldState, onMapCommand,
}) {
  const [activeCam, setActiveCam] = useState('front')  // 当前主摄像头

  // 缩略图：除当前主画面外的其他摄像头 + LiDAR
  const thumbCams = CAM_DIRECTIONS.filter(c => c.key !== activeCam)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: 6, overflow: 'hidden' }}>

      {/* 上栏: 左=摄像头(主画面+缩略图)  右=态势图  并排 */}
      <div style={{ display: 'flex', flexShrink: 0, height: 340, minHeight: 280, gap: 6 }}>

        {/* ── 左半: 摄像头主画面 + 左下角缩略图 ── */}
        <div style={{
          flex: 1, position: 'relative',
          background: '#0a0e14', borderRadius: 6, border: '1px solid rgba(34,197,94,0.15)',
          overflow: 'hidden',
        }}>
          {/* 主画面 */}
          {sensorCameras?.[activeCam]?.image ? (
            <img src={`data:image/jpeg;base64,${sensorCameras[activeCam].image}`}
              alt={activeCam}
              onDoubleClick={() => onOpenCockpit(CAM_DIRECTIONS.find(c => c.key === activeCam)?.cockpit)}
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', cursor: 'pointer' }} />
          ) : (
            <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'rgba(34,197,94,0.3)', fontSize: 14, fontFamily: 'monospace' }}>NO SIGNAL</div>
          )}

          {/* 主画面标签 */}
          <div style={{ position: 'absolute', top: 6, left: 8, padding: '2px 8px', borderRadius: 3,
            background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
            fontSize: 10, color: '#22c55e', fontFamily: 'monospace', letterSpacing: 1.5,
            textShadow: '0 0 6px rgba(34,197,94,0.5)' }}>
            {CAM_DIRECTIONS.find(c => c.key === activeCam)?.label}
          </div>

          {/* 扫描线效果 */}
          <div style={{ position: 'absolute', inset: 0,
            background: 'repeating-linear-gradient(0deg, transparent, transparent 3px, rgba(0,0,0,0.02) 3px, rgba(0,0,0,0.02) 6px)',
            pointerEvents: 'none' }} />

          {/* 左下角缩略图栏: 其他摄像头 + LiDAR */}
          <div style={{ position: 'absolute', bottom: 6, left: 6, display: 'flex', gap: 3, zIndex: 10 }}>
            {thumbCams.map(cam => (
              <div key={cam.key}
                onClick={() => setActiveCam(cam.key)}
                style={{
                  width: 64, height: 44, borderRadius: 4, overflow: 'hidden', cursor: 'pointer',
                  border: '1px solid rgba(34,197,94,0.3)', position: 'relative',
                  background: '#0a0e14', opacity: 0.85,
                  transition: 'opacity 0.15s, border-color 0.15s',
                }}
                onMouseEnter={e => { e.currentTarget.style.opacity = '1'; e.currentTarget.style.borderColor = '#22c55e' }}
                onMouseLeave={e => { e.currentTarget.style.opacity = '0.85'; e.currentTarget.style.borderColor = 'rgba(34,197,94,0.3)' }}
              >
                {sensorCameras?.[cam.key]?.image ? (
                  <img src={`data:image/jpeg;base64,${sensorCameras[cam.key].image}`} alt={cam.label}
                    style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
                ) : (
                  <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'rgba(34,197,94,0.25)', fontSize: 7, fontFamily: 'monospace' }}>OFFLINE</div>
                )}
                <span style={{ position: 'absolute', bottom: 1, left: 3, fontSize: 7, color: '#22c55e',
                  fontFamily: 'monospace', textShadow: '0 0 3px rgba(0,0,0,0.8)', letterSpacing: 0.5 }}>
                  {cam.label}
                </span>
              </div>
            ))}
            {/* LiDAR 缩略图 */}
            <div style={{
              width: 64, height: 44, borderRadius: 4, overflow: 'hidden',
              border: '1px solid rgba(34,197,94,0.3)', position: 'relative',
              background: '#0a0e14', opacity: 0.85,
            }}>
              <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <LidarRadar lidarData={sensorLidar} size={40} />
              </div>
              <span style={{ position: 'absolute', bottom: 1, left: 3, fontSize: 7, color: '#22c55e',
                fontFamily: 'monospace', textShadow: '0 0 3px rgba(0,0,0,0.8)' }}>◎ LIDAR</span>
            </div>
          </div>

          {/* 右下角双击提示 */}
          <div style={{ position: 'absolute', bottom: 6, right: 8, fontSize: 8, color: 'rgba(34,197,94,0.3)',
            fontFamily: 'monospace', zIndex: 10 }}>
            double-click → cockpit
          </div>
        </div>

        {/* ── 右半: 态势图 ── */}
        <div style={{
          flex: 1, position: 'relative',
          background: '#0a0e14', borderRadius: 6, border: '1px solid rgba(0,212,255,0.15)',
          overflow: 'hidden',
        }}>
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, zIndex: 6,
            display: 'flex', alignItems: 'center', gap: 6, padding: '3px 8px',
            background: 'rgba(10,14,20,0.8)', borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
            <span style={{ fontSize: 9, color: 'rgba(0,212,255,0.5)', fontFamily: 'monospace', letterSpacing: 1.5 }}>🗺 SITUATION MAP</span>
          </div>
          <div style={{ position: 'absolute', top: 22, left: 0, right: 0, bottom: 0 }}>
            <MapView socket={socket} worldState={worldState} onCommand={onMapCommand} />
          </div>
        </div>
      </div>

      {/* 下栏: 三栏活动面板 */}
      <div style={{ flex: 1, display: 'flex', gap: 4, minHeight: 0, overflow: 'hidden' }}>
        <LLMColumn aiStream={aiStream} aiThinking={aiThinking} />
        <PlanColumn aiThinking={aiThinking} lastAiPlan={lastAiPlan} logs={logs} />
        <SysLogColumn logs={logs} aiThinking={aiThinking} />
      </div>

      <style>{`
        .cursor-blink { animation: blink 1s step-end infinite; color: #a78bfa; font-size: 9px; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </div>
  )
}