/**
 * DeviceSetupPanel.jsx — 通用设备管理面板
 * Props: { socket, connected }
 *
 * 布局：左侧设备列表 + 右侧设备详情/传感器/控制
 */
import { useState, useEffect, useCallback, useRef } from 'react'

const DEVICE_TYPES = ['UAV', 'UGV', 'ARM', 'SENSOR', 'CUSTOM']
const PROTOCOLS    = ['http', 'mavlink', 'ros2', 'serial', 'custom']

const TYPE_COLOR = {
  UAV:    { bg: 'rgba(0,212,255,.08)',   border: 'rgba(0,212,255,.3)',   text: '#67e8f9' },
  UGV:    { bg: 'rgba(245,158,11,.08)',  border: 'rgba(245,158,11,.3)',  text: '#fbbf24' },
  ARM:    { bg: 'rgba(168,85,247,.08)',  border: 'rgba(168,85,247,.3)',  text: '#c084fc' },
  SENSOR: { bg: 'rgba(34,197,94,.08)',   border: 'rgba(34,197,94,.3)',   text: '#4ade80' },
  CUSTOM: { bg: 'rgba(148,163,184,.08)', border: 'rgba(148,163,184,.3)', text: '#94a3b8' },
}

const TYPE_ICON = { UAV: '✈️', UGV: '🚗', ARM: '🦾', SENSOR: '📡', CUSTOM: '⚙️' }

// 能力 → 颜色映射
const CAP_COLOR = {
  camera:       '#3b82f6',
  gps:          '#22c55e',
  accelerometer:'#f97316',
  gyroscope:    '#eab308',
  lidar:        '#a855f7',
  screen:       '#06b6d4',
  fly:          '#67e8f9',
  scan_lidar:   '#c084fc',
  capture_image:'#60a5fa',
}
const capColor = (cap) => CAP_COLOR[cap] || '#94a3b8'

// 快捷指令：能力 → { label, action, params }
const CAP_QUICK_ACTIONS = {
  camera:       { label: '拍照',   action: 'capture_image', params: {} },
  capture_image:{ label: '拍照',   action: 'capture_image', params: {} },
  gps:          { label: '获取位置', action: 'get_gps',    params: {} },
  screen:       { label: '截屏',   action: 'screenshot',   params: {} },
  fly:          { label: '起飞',   action: 'takeoff',      params: { altitude: 1.5 } },
  lidar:        { label: '扫描',   action: 'scan_lidar',   params: {} },
}

const S = {
  root: {
    display: 'flex', flexDirection: 'row', gap: 10,
    height: '100%', overflow: 'hidden',
    color: '#e2e8f0', fontSize: 13,
  },
  leftCol: {
    display: 'flex', flexDirection: 'column', gap: 10,
    width: 240, flexShrink: 0, overflow: 'hidden',
  },
  rightCol: {
    flex: 1, display: 'flex', flexDirection: 'column', gap: 10,
    overflow: 'hidden', minWidth: 0,
  },
  sectionTitle: {
    fontSize: 11, fontWeight: 700, color: '#00d4ff',
    textTransform: 'uppercase', letterSpacing: '0.06em',
    marginBottom: 6,
  },
  card: {
    background: 'rgba(15,23,42,.7)',
    border: '1px solid rgba(0,212,255,.15)',
    borderRadius: 8,
    padding: 12,
  },
  input: {
    width: '100%', boxSizing: 'border-box',
    background: 'rgba(255,255,255,.05)',
    border: '1px solid rgba(0,212,255,.2)',
    borderRadius: 6,
    color: '#e2e8f0', fontSize: 12, padding: '5px 9px',
    outline: 'none',
  },
  textarea: {
    width: '100%', boxSizing: 'border-box',
    background: 'rgba(255,255,255,.05)',
    border: '1px solid rgba(0,212,255,.2)',
    borderRadius: 6,
    color: '#e2e8f0', fontSize: 11, padding: '5px 9px',
    outline: 'none', fontFamily: 'monospace', resize: 'vertical',
    minHeight: 60,
  },
  select: {
    width: '100%', boxSizing: 'border-box',
    background: 'rgba(15,23,42,.9)',
    border: '1px solid rgba(0,212,255,.2)',
    borderRadius: 6,
    color: '#e2e8f0', fontSize: 12, padding: '5px 9px',
    outline: 'none',
  },
  btnPrimary: {
    background: 'linear-gradient(135deg,rgba(0,212,255,.2),rgba(0,212,255,.1))',
    border: '1px solid rgba(0,212,255,.5)',
    borderRadius: 6,
    color: '#00d4ff', fontSize: 12, fontWeight: 600,
    padding: '6px 14px', cursor: 'pointer',
  },
  btnDanger: {
    background: 'rgba(239,68,68,.1)',
    border: '1px solid rgba(239,68,68,.4)',
    borderRadius: 6,
    color: '#f87171', fontSize: 11,
    padding: '4px 8px', cursor: 'pointer',
  },
  btnGhost: {
    background: 'rgba(255,255,255,.05)',
    border: '1px solid rgba(255,255,255,.1)',
    borderRadius: 6,
    color: '#94a3b8', fontSize: 11,
    padding: '4px 10px', cursor: 'pointer',
  },
  label: { fontSize: 11, color: '#94a3b8', marginBottom: 3 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  dot: (ok) => ({
    width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
    background: ok ? '#22c55e' : '#ef4444',
    boxShadow: `0 0 5px ${ok ? '#22c55e88' : '#ef444488'}`,
  }),
  capTag: (cap) => ({
    fontSize: 10, padding: '2px 8px', borderRadius: 99,
    background: `${capColor(cap)}22`,
    border: `1px solid ${capColor(cap)}55`,
    color: capColor(cap),
  }),
  typeTag: (color) => ({
    fontSize: 10, padding: '1px 7px', borderRadius: 99,
    background: `${color}22`, border: `1px solid ${color}55`,
    color: color,
  }),
  emptyMsg: {
    textAlign: 'center', color: '#475569', fontSize: 12, padding: '18px 0',
  },
  toast: (ok) => ({
    position: 'fixed', bottom: 20, right: 20, zIndex: 9999,
    padding: '8px 16px', borderRadius: 8,
    background: ok ? 'rgba(34,197,94,.15)' : 'rgba(239,68,68,.15)',
    border: `1px solid ${ok ? 'rgba(34,197,94,.5)' : 'rgba(239,68,68,.5)'}`,
    color: ok ? '#4ade80' : '#f87171',
    fontSize: 12, fontWeight: 600,
  }),
  sensorCard: (flash) => ({
    background: flash ? 'rgba(0,212,255,.08)' : 'rgba(255,255,255,.03)',
    border: `1px solid ${flash ? 'rgba(0,212,255,.3)' : 'rgba(255,255,255,.08)'}`,
    borderRadius: 6, padding: '8px 10px',
    transition: 'background .3s, border-color .3s',
  }),
  resultBox: (ok) => ({
    background: ok ? 'rgba(34,197,94,.08)' : 'rgba(239,68,68,.08)',
    border: `1px solid ${ok ? 'rgba(34,197,94,.25)' : 'rgba(239,68,68,.25)'}`,
    borderRadius: 6, padding: '8px 10px',
    fontSize: 11, fontFamily: 'monospace', color: ok ? '#86efac' : '#fca5a5',
    whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 120, overflowY: 'auto',
  }),
}

function Toast({ msg, ok }) {
  if (!msg) return null
  return <div style={S.toast(ok)}>{msg}</div>
}

// ── 传感器值卡片（支持闪烁） ───────────────────────────────────────────────────
function SensorValueCard({ label, value }) {
  const [flash, setFlash] = useState(false)
  const prevVal = useRef(value)

  useEffect(() => {
    if (prevVal.current !== value) {
      prevVal.current = value
      setFlash(true)
      const t = setTimeout(() => setFlash(false), 500)
      return () => clearTimeout(t)
    }
  }, [value])

  const display = typeof value === 'object' && value !== null
    ? JSON.stringify(value, null, 1)
    : String(value ?? '—')

  return (
    <div style={S.sensorCard(flash)}>
      <div style={{ fontSize: 10, color: '#64748b', marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 12, color: '#e2e8f0', fontFamily: 'monospace', wordBreak: 'break-all' }}>
        {display}
      </div>
    </div>
  )
}

// ── AI 建档对话区 ─────────────────────────────────────────────────────────────
function OnboardChat({ deviceId }) {
  const [open, setOpen]               = useState(false)
  const [messages, setMessages]       = useState([])
  const [input, setInput]             = useState('')
  const [sending, setSending]         = useState(false)
  const [profileReady, setProfileReady] = useState(false)
  const historyRef = useRef(null)

  useEffect(() => {
    if (historyRef.current) {
      historyRef.current.scrollTop = historyRef.current.scrollHeight
    }
  }, [messages, sending])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', text }])
    setSending(true)
    try {
      const res = await fetch(`/api/device/${deviceId}/onboard`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'ai', text: data.reply || '…' }])
      if (data.profile_ready) setProfileReady(true)
    } catch (e) {
      setMessages(prev => [...prev, { role: 'ai', text: '请求失败: ' + e.message }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{ ...S.card, flexShrink: 0 }}>
      <div
        style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', userSelect: 'none' }}
        onClick={() => setOpen(v => !v)}
      >
        <span style={{ fontSize: 14, marginRight: 6 }}>🤖</span>
        <span style={{ ...S.sectionTitle, marginBottom: 0, flex: 1 }}>AI 建档</span>
        {profileReady && (
          <span style={{
            fontSize: 11, color: '#4ade80',
            background: 'rgba(34,197,94,.1)', border: '1px solid rgba(34,197,94,.3)',
            borderRadius: 99, padding: '1px 8px', marginRight: 8,
          }}>
            建档完成
          </span>
        )}
        <span style={{ color: '#475569', fontSize: 12 }}>{open ? '▲' : '▼'}</span>
      </div>

      {open && (
        <div style={{ marginTop: 10 }}>
          {/* 对话历史 */}
          <div
            ref={historyRef}
            style={{
              maxHeight: 250, overflowY: 'auto',
              display: 'flex', flexDirection: 'column', gap: 8,
              marginBottom: 10, paddingRight: 4,
            }}
          >
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', color: '#475569', fontSize: 12, padding: '20px 0' }}>
                开始与 AI 对话以建立设备档案
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                style={{ display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}
              >
                <div style={{
                  background: msg.role === 'ai' ? 'rgba(59,130,246,.18)' : 'rgba(34,197,94,.18)',
                  border: `1px solid ${msg.role === 'ai' ? 'rgba(59,130,246,.4)' : 'rgba(34,197,94,.4)'}`,
                  borderRadius: 12, padding: '8px 12px', maxWidth: '80%',
                  fontSize: 12, lineHeight: 1.5,
                  color: msg.role === 'ai' ? '#93c5fd' : '#86efac',
                  wordBreak: 'break-word',
                }}>
                  {msg.text}
                </div>
              </div>
            ))}
            {sending && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div style={{
                  background: 'rgba(59,130,246,.1)', border: '1px solid rgba(59,130,246,.3)',
                  borderRadius: 12, padding: '8px 12px', fontSize: 12, color: '#60a5fa',
                }}>
                  思考中…
                </div>
              </div>
            )}
          </div>

          {/* 输入区 */}
          <div style={{ display: 'flex', gap: 6 }}>
            <input
              style={{ ...S.input, flex: 1 }}
              placeholder="描述设备用途、场景…"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() } }}
              disabled={sending}
            />
            <button
              style={{ ...S.btnPrimary, flexShrink: 0 }}
              onClick={sendMessage}
              disabled={sending || !input.trim()}
            >
              发送
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── 技能绑定区 ────────────────────────────────────────────────────────────────
const SKILL_LAYERS = [
  { key: 'motor',      label: 'Motor Skills',      color: '#f97316' },
  { key: 'perception', label: 'Perception Skills',  color: '#22c55e' },
  { key: 'cognitive',  label: 'Cognitive Skills',   color: '#3b82f6' },
  { key: 'soft',       label: 'Soft Skills',        color: '#ec4899' },
]

const LAYER_LABELS_ZH = ['运动', '感知', '认知', '策略']

function SkillsSection({ deviceId }) {
  const [skills, setSkills]   = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!deviceId) return
    setLoading(true)
    fetch(`/api/device/${deviceId}/skills`)
      .then(r => r.json())
      .then(data => setSkills(data))
      .catch(() => setSkills(null))
      .finally(() => setLoading(false))
  }, [deviceId])

  if (loading) {
    return (
      <div style={{ color: '#475569', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>
        加载技能…
      </div>
    )
  }
  if (!skills) {
    return (
      <div style={{ color: '#475569', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>
        暂无技能数据
      </div>
    )
  }

  const counts = SKILL_LAYERS.map(layer => (skills[layer.key] || []).length)
  const total  = counts.reduce((a, b) => a + b, 0)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {SKILL_LAYERS.map((layer, idx) => {
        const layerSkills = skills[layer.key] || []
        return (
          <div key={layer.key}>
            <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>{layer.label}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap' }}>
              {layerSkills.length === 0 ? (
                <span style={{ fontSize: 11, color: '#334155' }}>—</span>
              ) : (
                layerSkills.map((skill, si) => {
                  const name   = typeof skill === 'string' ? skill : (skill.name || skill.skill || String(si))
                  const active = typeof skill === 'string' ? true : (skill.suspended !== true && skill.active !== false)
                  return (
                    <span
                      key={name}
                      style={{
                        padding: '4px 10px', borderRadius: 12,
                        fontSize: 12, margin: 3,
                        background:  active ? `${layer.color}22` : 'rgba(148,163,184,.08)',
                        border: `1px solid ${active ? layer.color + '55' : 'rgba(148,163,184,.25)'}`,
                        color: active ? layer.color : '#475569',
                      }}
                    >
                      {name}
                    </span>
                  )
                })
              )}
            </div>
          </div>
        )
      })}
      <div style={{
        fontSize: 11, color: '#475569',
        borderTop: '1px solid rgba(255,255,255,.06)', paddingTop: 8,
      }}>
        共 {total} 个技能（{counts.map((c, i) => `${c} ${LAYER_LABELS_ZH[i]}`).join(' + ')}）
      </div>
    </div>
  )
}

// ── 传感器数据区 ──────────────────────────────────────────────────────────────
function SensorSection({ state }) {
  if (!state || Object.keys(state).length === 0) {
    return (
      <div style={{ color: '#475569', fontSize: 12, textAlign: 'center', padding: '12px 0' }}>
        暂无传感器数据
      </div>
    )
  }

  // 已知字段的显示名
  const LABELS = {
    battery:      '电量 %',
    latitude:     '纬度',
    longitude:    '经度',
    altitude:     '高度 m',
    speed:        '速度 m/s',
    heading:      '朝向 °',
    roll:         '横滚 °',
    pitch:        '俯仰 °',
    yaw:          '偏航 °',
    accel_x:      '加速度 X',
    accel_y:      '加速度 Y',
    accel_z:      '加速度 Z',
    temperature:  '温度 °C',
    pressure:     '气压 hPa',
    armed:        '解锁',
    mode:         '飞行模式',
    gps_fix:      'GPS Fix',
    satellites:   '卫星数',
    position:     '位置 (GPS)',
    acceleration: '加速度',
    orientation:  '朝向',
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
      {Object.entries(state).map(([k, v]) => (
        <SensorValueCard key={k} label={LABELS[k] || k} value={v} />
      ))}
    </div>
  )
}

// ── 设备详情右侧面板 ──────────────────────────────────────────────────────────
function DeviceDetail({ device, deviceState, socket, showToast }) {
  const [cmdName, setCmdName]   = useState('')
  const [cmdParams, setCmdParams] = useState('{}')
  const [sending, setSending]   = useState(false)
  const [cmdResult, setCmdResult] = useState(null) // { ok, text }

  const tc = TYPE_COLOR[device.type] || TYPE_COLOR.CUSTOM
  const online = device.status === 'online' || device.status === 'idle' || device.status === 'active'
  const caps = Array.isArray(device.capabilities) ? device.capabilities : []
  const hb = device.last_heartbeat
    ? new Date(device.last_heartbeat * 1000).toLocaleTimeString()
    : '—'
  const regTime = device.registered_at
    ? new Date(device.registered_at * 1000).toLocaleString()
    : '—'

  const sendCommand = async (action, params) => {
    const actionName = action || cmdName.trim()
    if (!actionName) { showToast('请输入指令名称', false); return }

    let parsedParams = params
    if (parsedParams === undefined) {
      try {
        parsedParams = JSON.parse(cmdParams || '{}')
      } catch {
        showToast('参数 JSON 格式错误', false); return
      }
    }

    setSending(true)
    setCmdResult(null)
    try {
      const res = await fetch(`/api/device/${device.device_id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: device.device_id,
          action: actionName,
          params: parsedParams,
        }),
      })
      const data = await res.json()
      if (res.ok) {
        setCmdResult({ ok: true, text: JSON.stringify(data, null, 2) })
        showToast(`指令 ${actionName} 已发送`, true)
      } else {
        setCmdResult({ ok: false, text: data.error || JSON.stringify(data, null, 2) })
        showToast(data.error || '指令发送失败', false)
      }
    } catch (e) {
      setCmdResult({ ok: false, text: e.message })
      showToast('请求失败: ' + e.message, false)
    } finally {
      setSending(false)
    }
  }

  // 快捷指令：从 capabilities 过滤
  const quickActions = caps
    .filter(c => CAP_QUICK_ACTIONS[c])
    .map(c => ({ cap: c, ...CAP_QUICK_ACTIONS[c] }))
    // 去重（同 action 只留一个）
    .filter((item, idx, arr) => arr.findIndex(x => x.action === item.action) === idx)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%', overflowY: 'auto', paddingRight: 2 }}>

      {/* 设备基本信息 */}
      <div style={{ ...S.card, flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <span style={{ fontSize: 20 }}>{TYPE_ICON[device.type] || '⚙️'}</span>
          <span style={{ fontWeight: 700, color: tc.text, fontSize: 15 }}>{device.device_id}</span>
          <span style={S.typeTag(tc.text)}>{device.type}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginLeft: 'auto' }}>
            <div style={S.dot(online)} />
            <span style={{ fontSize: 11, color: online ? '#4ade80' : '#f87171' }}>
              {device.status || 'unknown'}
            </span>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 11, marginBottom: 10 }}>
          <div>
            <span style={{ color: '#475569' }}>协议: </span>
            <span style={{ color: '#94a3b8' }}>{device.protocol || '—'}</span>
          </div>
          <div>
            <span style={{ color: '#475569' }}>心跳: </span>
            <span style={{ color: '#94a3b8' }}>{hb}</span>
          </div>
          <div style={{ gridColumn: '1/-1' }}>
            <span style={{ color: '#475569' }}>注册时间: </span>
            <span style={{ color: '#94a3b8' }}>{regTime}</span>
          </div>
        </div>

        {/* 能力标签 */}
        {caps.length > 0 && (
          <div>
            <div style={{ ...S.label, marginBottom: 5 }}>能力</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {caps.map(c => (
                <span key={c} style={S.capTag(c)}>{c}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* AI 建档对话区 */}
      <OnboardChat deviceId={device.device_id} />

      {/* 传感器数据 */}
      <div style={{ ...S.card, flexShrink: 0 }}>
        <div style={S.sectionTitle}>实时传感器数据</div>
        <SensorSection state={deviceState} />
      </div>

      {/* 技能绑定区 */}
      <div style={{ ...S.card, flexShrink: 0 }}>
        <div style={S.sectionTitle}>技能绑定</div>
        <SkillsSection deviceId={device.device_id} />
      </div>

      {/* 发送指令 */}
      <div style={{ ...S.card, flexShrink: 0 }}>
        <div style={S.sectionTitle}>发送指令</div>

        {/* 快捷按钮 */}
        {quickActions.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 8 }}>
            {quickActions.map(({ cap, label, action, params }) => (
              <button
                key={action}
                style={{ ...S.btnGhost, borderColor: `${capColor(cap)}55`, color: capColor(cap) }}
                onClick={() => sendCommand(action, params)}
                disabled={sending}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div>
            <div style={S.label}>指令名称</div>
            <input
              style={S.input}
              placeholder="如 capture_image"
              value={cmdName}
              onChange={e => setCmdName(e.target.value)}
            />
          </div>
          <div>
            <div style={S.label}>参数 JSON</div>
            <textarea
              style={S.textarea}
              value={cmdParams}
              onChange={e => setCmdParams(e.target.value)}
              spellCheck={false}
            />
          </div>
          <button
            style={{ ...S.btnPrimary, width: '100%', padding: '7px 0' }}
            onClick={() => sendCommand()}
            disabled={sending}
          >
            {sending ? '发送中…' : '▶ 发送指令'}
          </button>

          {cmdResult && (
            <div style={S.resultBox(cmdResult.ok)}>
              {cmdResult.text}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── 主面板 ────────────────────────────────────────────────────────────────────
export default function DeviceSetupPanel({ socket, connected }) {
  const [devices, setDevices]       = useState([])
  const [loading, setLoading]       = useState(false)
  const [toast, setToast]           = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  // device_id → state dict
  const [deviceStates, setDeviceStates] = useState({})

  // 注册表单
  const [form, setForm] = useState({
    device_id:    '',
    device_type:  'UAV',
    capabilities: '',
    protocol:     'http',
  })
  const [registering, setRegistering] = useState(false)
  const [showRegForm, setShowRegForm] = useState(false)

  const showToast = (msg, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3000)
  }

  // ── 数据获取 ─────────────────────────────────────────────────────────────────
  const fetchDevices = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/devices')
      const data = await res.json()
      setDevices(Array.isArray(data) ? data : (data.devices || []))
    } catch (e) {
      showToast('获取设备列表失败: ' + e.message, false)
    } finally {
      setLoading(false)
    }
  }, [])

  // ── WebSocket 监听 ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!socket) return

    const refresh = () => fetchDevices()

    const onState = (payload) => {
      const id = payload?.device_id
      if (!id) return
      setDeviceStates(prev => ({
        ...prev,
        [id]: { ...(prev[id] || {}), ...(payload.state || payload) },
      }))
    }

    socket.on('device_registered',   refresh)
    socket.on('device_unregistered', refresh)
    socket.on('device_online',       refresh)
    socket.on('device_offline',      refresh)
    socket.on('device_state',        onState)

    return () => {
      socket.off('device_registered',   refresh)
      socket.off('device_unregistered', refresh)
      socket.off('device_online',       refresh)
      socket.off('device_offline',      refresh)
      socket.off('device_state',        onState)
    }
  }, [socket, fetchDevices])

  useEffect(() => { fetchDevices() }, [fetchDevices])

  // 选中设备失效时清除选中
  useEffect(() => {
    if (selectedId && !devices.find(d => d.device_id === selectedId)) {
      setSelectedId(null)
    }
  }, [devices, selectedId])

  // ── 注册 ─────────────────────────────────────────────────────────────────────
  const handleRegister = async () => {
    if (!form.device_id.trim()) { showToast('请输入 device_id', false); return }
    setRegistering(true)
    try {
      const caps = form.capabilities
        .split(',').map(s => s.trim()).filter(Boolean)
      const res = await fetch('/api/device/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id:    form.device_id.trim(),
          device_type:  form.device_type,
          capabilities: caps,
          sensors:      [],
          protocol:     form.protocol,
        }),
      })
      const data = await res.json()
      if (res.ok) {
        showToast(`设备 ${form.device_id} 注册成功`, true)
        setForm(f => ({ ...f, device_id: '', capabilities: '' }))
        setShowRegForm(false)
        fetchDevices()
      } else {
        showToast(data.error || '注册失败', false)
      }
    } catch (e) {
      showToast('注册请求失败: ' + e.message, false)
    } finally {
      setRegistering(false)
    }
  }

  // ── 注销 ─────────────────────────────────────────────────────────────────────
  const handleUnregister = async (deviceId) => {
    try {
      const res = await fetch(`/api/device/${encodeURIComponent(deviceId)}`, {
        method: 'DELETE',
      })
      const data = await res.json()
      if (res.ok) {
        showToast(`设备 ${deviceId} 已注销`, true)
        if (selectedId === deviceId) setSelectedId(null)
        fetchDevices()
      } else {
        showToast(data.error || '注销失败', false)
      }
    } catch (e) {
      showToast('注销请求失败: ' + e.message, false)
    }
  }

  const selectedDevice = devices.find(d => d.device_id === selectedId)

  // ── UI ───────────────────────────────────────────────────────────────────────
  return (
    <div style={S.root}>
      <Toast msg={toast?.msg} ok={toast?.ok} />

      {/* ── 左侧：设备列表 ── */}
      <div style={S.leftCol}>

        {/* 顶部状态栏 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <div style={S.dot(connected)} />
          <span style={{ fontSize: 11, color: connected ? '#4ade80' : '#f87171' }}>
            {connected ? '已连接' : '断开'}
          </span>
          <span style={{ fontSize: 11, color: '#475569', marginLeft: 'auto' }}>
            {devices.length} 台
          </span>
          <button
            onClick={fetchDevices}
            disabled={loading}
            style={{ ...S.btnPrimary, padding: '3px 8px', fontSize: 11 }}
          >
            {loading ? '…' : '↻'}
          </button>
        </div>

        {/* 设备列表 */}
        <div style={{ ...S.card, flex: 1, overflowY: 'auto', minHeight: 0 }}>
          <div style={S.sectionTitle}>已接入设备</div>
          {devices.length === 0 && !loading && (
            <div style={S.emptyMsg}>暂无设备</div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {devices.map(dev => {
              const tc = TYPE_COLOR[dev.type] || TYPE_COLOR.CUSTOM
              const online = dev.status === 'online' || dev.status === 'idle' || dev.status === 'active'
              const isSelected = dev.device_id === selectedId

              return (
                <div
                  key={dev.device_id}
                  onClick={() => setSelectedId(isSelected ? null : dev.device_id)}
                  style={{
                    background: isSelected ? tc.bg : 'rgba(255,255,255,.02)',
                    border: `1px solid ${isSelected ? tc.border : 'rgba(255,255,255,.07)'}`,
                    borderRadius: 7,
                    padding: '8px 10px',
                    cursor: 'pointer',
                    transition: 'all .15s',
                  }}
                >
                  {/* 头部 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <span style={{ fontSize: 14 }}>{TYPE_ICON[dev.type] || '⚙️'}</span>
                    <span style={{ fontWeight: 700, color: tc.text, fontSize: 12, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {dev.device_id}
                    </span>
                    <div style={S.dot(online)} />
                  </div>

                  {/* 子信息 */}
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span style={S.typeTag(tc.text)}>{dev.type}</span>
                    <span style={{ fontSize: 10, color: '#475569', flex: 1 }}>{dev.protocol}</span>
                    <button
                      onClick={e => { e.stopPropagation(); handleUnregister(dev.device_id) }}
                      style={{ ...S.btnDanger, padding: '2px 6px', fontSize: 10 }}
                    >
                      注销
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* 注册按钮 / 表单 */}
        <div style={{ ...S.card, flexShrink: 0 }}>
          <div
            style={{ ...S.sectionTitle, cursor: 'pointer', display: 'flex', alignItems: 'center' }}
            onClick={() => setShowRegForm(v => !v)}
          >
            注册新设备
            <span style={{ marginLeft: 'auto', fontWeight: 400, fontSize: 12 }}>
              {showRegForm ? '▲' : '▼'}
            </span>
          </div>

          {showRegForm && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              <div>
                <div style={S.label}>Device ID *</div>
                <input
                  style={S.input}
                  placeholder="如 uav_001"
                  value={form.device_id}
                  onChange={e => setForm(f => ({ ...f, device_id: e.target.value }))}
                />
              </div>

              <div style={S.grid2}>
                <div>
                  <div style={S.label}>类型</div>
                  <select
                    style={S.select}
                    value={form.device_type}
                    onChange={e => setForm(f => ({ ...f, device_type: e.target.value }))}
                  >
                    {DEVICE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <div style={S.label}>协议</div>
                  <select
                    style={S.select}
                    value={form.protocol}
                    onChange={e => setForm(f => ({ ...f, protocol: e.target.value }))}
                  >
                    {PROTOCOLS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
              </div>

              <div>
                <div style={S.label}>能力（逗号分隔）</div>
                <input
                  style={S.input}
                  placeholder="如 fly,camera,gps"
                  value={form.capabilities}
                  onChange={e => setForm(f => ({ ...f, capabilities: e.target.value }))}
                />
              </div>

              <button
                onClick={handleRegister}
                disabled={registering}
                style={{ ...S.btnPrimary, width: '100%', padding: '6px 0' }}
              >
                {registering ? '注册中…' : '+ 注册'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── 右侧：设备详情 ── */}
      <div style={S.rightCol}>
        {selectedDevice ? (
          <DeviceDetail
            device={selectedDevice}
            deviceState={deviceStates[selectedDevice.device_id]}
            socket={socket}
            showToast={showToast}
          />
        ) : (
          <div style={{
            flex: 1, display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: 10,
            color: '#334155',
          }}>
            <span style={{ fontSize: 40 }}>📋</span>
            <span style={{ fontSize: 14 }}>请在左侧选择一个设备</span>
            <span style={{ fontSize: 12, color: '#1e3a5f' }}>点击设备卡片查看详情、传感器数据和控制面板</span>
          </div>
        )}
      </div>
    </div>
  )
}
