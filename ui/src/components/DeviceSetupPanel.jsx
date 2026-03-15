/**
 * DeviceSetupPanel.jsx — 通用设备管理面板
 * Props: { socket, connected }
 */
import { useState, useEffect, useCallback } from 'react'

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

const S = {
  panel: {
    display: 'flex', flexDirection: 'column', gap: 10,
    height: '100%', overflow: 'hidden',
    color: '#e2e8f0', fontSize: 13,
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
  label: { fontSize: 11, color: '#94a3b8', marginBottom: 3 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 },
  dot: (ok) => ({
    width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
    background: ok ? '#22c55e' : '#ef4444',
    boxShadow: `0 0 5px ${ok ? '#22c55e88' : '#ef444488'}`,
  }),
  tag: (color) => ({
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
    animation: 'fadeIn .2s ease',
  }),
}

function Toast({ msg, ok }) {
  if (!msg) return null
  return <div style={S.toast(ok)}>{msg}</div>
}

export default function DeviceSetupPanel({ socket, connected }) {
  const [devices, setDevices]     = useState([])
  const [loading, setLoading]     = useState(false)
  const [toast, setToast]         = useState(null)   // { msg, ok }

  // 注册表单
  const [form, setForm] = useState({
    device_id:   '',
    device_type: 'UAV',
    capabilities: '',
    protocol:    'http',
  })
  const [registering, setRegistering] = useState(false)

  // ── 数据获取 ────────────────────────────────────────────────────────────────
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

  const showToast = (msg, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3000)
  }

  // ── WebSocket 监听 ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!socket) return
    const refresh = () => fetchDevices()
    socket.on('device_registered',   refresh)
    socket.on('device_unregistered', refresh)
    socket.on('device_online',       refresh)
    socket.on('device_offline',      refresh)
    return () => {
      socket.off('device_registered',   refresh)
      socket.off('device_unregistered', refresh)
      socket.off('device_online',       refresh)
      socket.off('device_offline',      refresh)
    }
  }, [socket, fetchDevices])

  useEffect(() => { fetchDevices() }, [fetchDevices])

  // ── 注册 ────────────────────────────────────────────────────────────────────
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
          device_id:   form.device_id.trim(),
          device_type: form.device_type,
          capabilities: caps,
          sensors: [],
          protocol: form.protocol,
        }),
      })
      const data = await res.json()
      if (res.ok) {
        showToast(`设备 ${form.device_id} 注册成功`, true)
        setForm(f => ({ ...f, device_id: '', capabilities: '' }))
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

  // ── 注销 ────────────────────────────────────────────────────────────────────
  const handleUnregister = async (deviceId) => {
    try {
      const res = await fetch(`/api/device/${encodeURIComponent(deviceId)}`, {
        method: 'DELETE',
      })
      const data = await res.json()
      if (res.ok) {
        showToast(`设备 ${deviceId} 已注销`, true)
        fetchDevices()
      } else {
        showToast(data.error || '注销失败', false)
      }
    } catch (e) {
      showToast('注销请求失败: ' + e.message, false)
    }
  }

  // ── UI ──────────────────────────────────────────────────────────────────────
  return (
    <div style={S.panel}>
      <Toast msg={toast?.msg} ok={toast?.ok} />

      {/* 连接状态栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <div style={S.dot(connected)} />
        <span style={{ fontSize: 11, color: connected ? '#4ade80' : '#f87171' }}>
          {connected ? 'WebSocket 已连接' : 'WebSocket 断开'}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#475569' }}>
          {devices.length} 台设备
        </span>
        <button
          onClick={fetchDevices}
          disabled={loading}
          style={{ ...S.btnPrimary, padding: '3px 10px', fontSize: 11 }}
        >
          {loading ? '刷新中…' : '↻ 刷新'}
        </button>
      </div>

      {/* 已接入设备列表 */}
      <div style={{ ...S.card, flex: 1, overflowY: 'auto', minHeight: 0 }}>
        <div style={S.sectionTitle}>已接入设备</div>
        {devices.length === 0 && !loading && (
          <div style={S.emptyMsg}>暂无已接入设备</div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {devices.map(dev => {
            const tc = TYPE_COLOR[dev.type] || TYPE_COLOR.CUSTOM
            const online = dev.status === 'online' || dev.status === 'idle' || dev.status === 'active'
            const caps   = Array.isArray(dev.capabilities) ? dev.capabilities : []
            const hb     = dev.last_heartbeat
              ? new Date(dev.last_heartbeat * 1000).toLocaleTimeString()
              : '—'

            return (
              <div
                key={dev.device_id}
                style={{
                  background: tc.bg,
                  border: `1px solid ${tc.border}`,
                  borderRadius: 8,
                  padding: '10px 12px',
                }}
              >
                {/* 头部行 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 16 }}>{TYPE_ICON[dev.type] || '⚙️'}</span>
                  <span style={{ fontWeight: 700, color: tc.text, fontSize: 13 }}>
                    {dev.device_id}
                  </span>
                  <span style={S.tag(tc.text)}>{dev.type}</span>
                  {/* 状态点 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <div style={S.dot(online)} />
                    <span style={{ fontSize: 10, color: online ? '#4ade80' : '#f87171' }}>
                      {dev.status || 'unknown'}
                    </span>
                  </div>
                  {/* 注销按钮 */}
                  <button
                    onClick={() => handleUnregister(dev.device_id)}
                    style={{ ...S.btnDanger, marginLeft: 'auto' }}
                  >
                    注销
                  </button>
                </div>

                {/* 详情行 */}
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 11, color: '#94a3b8' }}>
                  <span>
                    <span style={{ color: '#475569' }}>能力: </span>
                    {caps.length ? caps.join(', ') : '—'}
                  </span>
                  <span>
                    <span style={{ color: '#475569' }}>心跳: </span>
                    {hb}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 注册表单 */}
      <div style={{ ...S.card, flexShrink: 0 }}>
        <div style={S.sectionTitle}>注册新设备</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

          {/* device_id */}
          <div>
            <div style={S.label}>Device ID *</div>
            <input
              style={S.input}
              placeholder="如 uav_001"
              value={form.device_id}
              onChange={e => setForm(f => ({ ...f, device_id: e.target.value }))}
            />
          </div>

          {/* type + protocol */}
          <div style={S.grid2}>
            <div>
              <div style={S.label}>设备类型</div>
              <select
                style={S.select}
                value={form.device_type}
                onChange={e => setForm(f => ({ ...f, device_type: e.target.value }))}
              >
                {DEVICE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <div style={S.label}>通信协议</div>
              <select
                style={S.select}
                value={form.protocol}
                onChange={e => setForm(f => ({ ...f, protocol: e.target.value }))}
              >
                {PROTOCOLS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>

          {/* capabilities */}
          <div>
            <div style={S.label}>能力列表（逗号分隔）</div>
            <input
              style={S.input}
              placeholder="如 fly,capture_image,scan_lidar"
              value={form.capabilities}
              onChange={e => setForm(f => ({ ...f, capabilities: e.target.value }))}
            />
          </div>

          {/* 注册按钮 */}
          <button
            onClick={handleRegister}
            disabled={registering}
            style={{ ...S.btnPrimary, width: '100%', padding: '7px 0' }}
          >
            {registering ? '注册中…' : '+ 注册设备'}
          </button>
        </div>
      </div>
    </div>
  )
}
