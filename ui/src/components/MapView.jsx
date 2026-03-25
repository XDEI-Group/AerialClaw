/**
 * MapView.jsx — 实时态势图 + 交互式指挥
 *
 * 功能:
 *   - 无人机实时位置 (脉冲蓝点) + 飞行轨迹
 *   - 地标标注 (金色, 从 WORLD_MAP.md 加载 + update_map 实时追加)
 *   - 报告/警报位置标注
 *   - 点击地图 → 弹出指令输入框 → 发送给无人机 AI
 *   - 缩放拖拽
 */
import { useState, useEffect, useRef } from 'react'

function ned2c(n, e, cx, cy, s) { return { x: cx + e * s, y: cy - n * s } }
function c2ned(px, py, cx, cy, s) { return { n: -(py - cy) / s, e: (px - cx) / s } }

export default function MapView({ socket, worldState, onCommand }) {
  const canvasRef = useRef(null)
  const boxRef = useRef(null)
  const [trail, setTrail] = useState([])
  const [landmarks, setLandmarks] = useState([])
  const [reports, setReports] = useState([])
  const [alerts, setAlerts] = useState([])
  const [drone, setDrone] = useState({ n: 0, e: 0, d: 0 })
  const [scale, setScale] = useState(1.5)
  const [off, setOff] = useState({ x: 0, y: 0 })
  const [drag, setDrag] = useState(false)
  const dRef = useRef({ x: 0, y: 0, ox: 0, oy: 0 })
  const [sz, setSz] = useState({ w: 600, h: 400 })
  const anim = useRef(null)

  // 点击交互
  const [clickPos, setClickPos] = useState(null)  // {px, py, n, e} canvas+NED坐标
  const [cmdText, setCmdText] = useState('')
  const [showInput, setShowInput] = useState(false)
  const inputRef = useRef(null)

  // 更新位置
  useEffect(() => {
    if (!worldState?.robots?.UAV_1?.position) return
    const p = worldState.robots.UAV_1.position
    // position 可能是数组 [n,e,d] 或对象 {north,east,down}
    const n = Array.isArray(p) ? (p[0] || 0) : (p.north || 0)
    const e = Array.isArray(p) ? (p[1] || 0) : (p.east || 0)
    const d = Array.isArray(p) ? (p[2] || 0) : (p.down || 0)
    setDrone({ n, e, d })
    setTrail(prev => {
      const l = prev[prev.length - 1]
      if (l && Math.abs(l.n - n) < 0.3 && Math.abs(l.e - e) < 0.3) return prev
      const next = [...prev, { n, e }]
      return next.length > 2000 ? next.slice(-2000) : next
    })
  }, [worldState])

  // Socket 监听
  useEffect(() => {
    if (!socket) return
    // 新地标实时推送
    const onLandmark = (data) => {
      setLandmarks(prev => {
        const exists = prev.some(l => l.name === data.name)
        if (exists) return prev
        return [...prev, { name: data.name, n: data.n, e: data.e, desc: data.desc }]
      })
    }
    // 报告位置实时推送
    const onMapReport = (data) => {
      setReports(prev => [...prev, { n: data.n, e: data.e, s: data.severity || 'info', content: data.content }])
    }
    // 警报
    const onChat = (data) => {
      if (data?.intent === 'alert') {
        const m = data.reply?.match(/\((-?\d+),\s*(-?\d+)/)
        if (m) setAlerts(prev => [...prev, { n: +m[1], e: +m[2], l: data.level || 'warning' }])
      }
    }
    socket.on('map_landmark', onLandmark)
    socket.on('map_report', onMapReport)
    socket.on('ai_chat_reply', onChat)
    return () => {
      socket.off('map_landmark', onLandmark)
      socket.off('map_report', onMapReport)
      socket.off('ai_chat_reply', onChat)
    }
  }, [socket])

  // 加载地标
  useEffect(() => {
    fetch('/api/map/landmarks').then(r => r.json()).then(d => { if (d.landmarks) setLandmarks(d.landmarks) }).catch(() => {})
  }, [])

  // 尺寸自适应
  useEffect(() => {
    const el = boxRef.current; if (!el) return
    const obs = new ResizeObserver(e => { const { width, height } = e[0].contentRect; setSz({ w: Math.floor(width), h: Math.floor(height) }) })
    obs.observe(el); return () => obs.disconnect()
  }, [])

  // 自动缩放
  useEffect(() => {
    const pts = [...trail, ...landmarks.map(l => ({ n: l.n, e: l.e }))]
    if (pts.length < 2) { setScale(1.5); return }
    const minN = Math.min(...pts.map(p => p.n)) - 40, maxN = Math.max(...pts.map(p => p.n)) + 40
    const minE = Math.min(...pts.map(p => p.e)) - 40, maxE = Math.max(...pts.map(p => p.e)) + 40
    const fit = Math.min(sz.w * 0.8 / (maxE - minE || 100), sz.h * 0.8 / (maxN - minN || 100))
    setScale(Math.max(0.1, Math.min(5, fit)))
  }, [trail.length > 0 && trail.length % 20 === 0, landmarks.length, sz])

  // 绘制
  useEffect(() => {
    const draw = () => {
      const c = canvasRef.current; if (!c) return
      const ctx = c.getContext('2d'), { w, h } = sz, dpr = window.devicePixelRatio || 1
      c.width = w * dpr; c.height = h * dpr; ctx.scale(dpr, dpr)
      ctx.fillStyle = '#0a0e17'; ctx.fillRect(0, 0, w, h)
      const cx = w / 2 + off.x, cy = h / 2 + off.y

      // 网格
      const gs = 50 * scale
      if (gs > 8) {
        ctx.strokeStyle = 'rgba(100,200,255,0.06)'; ctx.lineWidth = 0.5
        for (let x = cx % gs; x < w; x += gs) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke() }
        for (let y = cy % gs; y < h; y += gs) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke() }
      }

      // 原点
      const o = ned2c(0, 0, cx, cy, scale)
      ctx.strokeStyle = 'rgba(0,212,255,0.3)'; ctx.lineWidth = 1
      ctx.beginPath(); ctx.moveTo(o.x - 10, o.y); ctx.lineTo(o.x + 10, o.y); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(o.x, o.y - 10); ctx.lineTo(o.x, o.y + 10); ctx.stroke()
      ctx.fillStyle = 'rgba(0,212,255,0.5)'; ctx.font = '10px monospace'; ctx.fillText('HOME', o.x + 12, o.y - 5)

      // 方向指示
      ctx.fillStyle = 'rgba(255,255,255,0.4)'; ctx.font = '11px sans-serif'
      ctx.fillText('N \u2191', cx - 8, 18); ctx.fillText('E \u2192', w - 28, cy + 4)
      ctx.fillText('S \u2193', cx - 8, h - 8); ctx.fillText('\u2190 W', 4, cy + 4)

      // 地标 (金色圆点 + 名称)
      landmarks.forEach(lm => {
        const p = ned2c(lm.n, lm.e, cx, cy, scale)
        // 外圈
        ctx.strokeStyle = 'rgba(255,200,50,0.4)'; ctx.lineWidth = 1
        ctx.beginPath(); ctx.arc(p.x, p.y, 7, 0, Math.PI * 2); ctx.stroke()
        // 内点
        ctx.fillStyle = 'rgba(255,200,50,0.8)'; ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, Math.PI * 2); ctx.fill()
        // 名称
        ctx.fillStyle = 'rgba(255,200,50,0.9)'; ctx.font = '10px sans-serif'; ctx.fillText(lm.name || '?', p.x + 10, p.y - 2)
      })

      // 报告点 (三角)
      reports.forEach(r => {
        const p = ned2c(r.n, r.e, cx, cy, scale)
        ctx.fillStyle = r.s === 'warning' ? '#ffa500' : '#00d4ff'
        ctx.beginPath(); ctx.moveTo(p.x, p.y - 7); ctx.lineTo(p.x - 5, p.y + 3); ctx.lineTo(p.x + 5, p.y + 3); ctx.closePath(); ctx.fill()
      })

      // 警报 (闪烁红圈)
      alerts.forEach(a => {
        const p = ned2c(a.n, a.e, cx, cy, scale)
        if (Math.sin(Date.now() / 200) > 0) { ctx.fillStyle = 'rgba(255,0,0,0.35)'; ctx.beginPath(); ctx.arc(p.x, p.y, 12, 0, Math.PI * 2); ctx.fill() }
        ctx.fillStyle = '#ff4444'; ctx.font = '16px sans-serif'; ctx.fillText('\u26a0', p.x - 8, p.y + 6)
      })

      // 轨迹 (渐变青色线)
      if (trail.length > 1) {
        ctx.beginPath(); ctx.strokeStyle = 'rgba(0,212,255,0.5)'; ctx.lineWidth = 1.5
        const f = ned2c(trail[0].n, trail[0].e, cx, cy, scale); ctx.moveTo(f.x, f.y)
        for (let i = 1; i < trail.length; i++) { const p = ned2c(trail[i].n, trail[i].e, cx, cy, scale); ctx.lineTo(p.x, p.y) }
        ctx.stroke()
        // 最后一段高亮
        if (trail.length > 2) {
          const last2 = trail.slice(-10)
          ctx.beginPath(); ctx.strokeStyle = 'rgba(0,212,255,0.9)'; ctx.lineWidth = 2
          const lf = ned2c(last2[0].n, last2[0].e, cx, cy, scale); ctx.moveTo(lf.x, lf.y)
          for (let i = 1; i < last2.length; i++) { const p = ned2c(last2[i].n, last2[i].e, cx, cy, scale); ctx.lineTo(p.x, p.y) }
          ctx.stroke()
        }
      }

      // 无人机图标 (俯视四旋翼)
      const dp = ned2c(drone.n, drone.e, cx, cy, scale)
      const pulse = 8 + Math.sin(Date.now() / 300) * 3
      // 脉冲光环
      ctx.beginPath(); ctx.fillStyle = 'rgba(0,212,255,0.06)'; ctx.arc(dp.x, dp.y, pulse + 12, 0, Math.PI * 2); ctx.fill()
      ctx.beginPath(); ctx.fillStyle = 'rgba(0,212,255,0.12)'; ctx.arc(dp.x, dp.y, pulse + 4, 0, Math.PI * 2); ctx.fill()
      // 机体 (俯视四旋翼轮廓)
      const S = 10  // 图标半尺寸
      ctx.save()
      ctx.translate(dp.x, dp.y)
      // 机臂 (X 形)
      ctx.strokeStyle = '#00d4ff'; ctx.lineWidth = 2; ctx.lineCap = 'round'
      ctx.beginPath(); ctx.moveTo(-S, -S); ctx.lineTo(S, S); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(S, -S); ctx.lineTo(-S, S); ctx.stroke()
      // 四个旋翼圆
      const rotorR = S * 0.55
      const arms = [[-S, -S], [S, -S], [S, S], [-S, S]]
      arms.forEach(([ax, ay]) => {
        ctx.beginPath(); ctx.strokeStyle = 'rgba(0,212,255,0.6)'; ctx.lineWidth = 1.5
        ctx.arc(ax, ay, rotorR, 0, Math.PI * 2); ctx.stroke()
        ctx.beginPath(); ctx.fillStyle = 'rgba(0,212,255,0.25)'
        ctx.arc(ax, ay, rotorR, 0, Math.PI * 2); ctx.fill()
      })
      // 中心机体
      ctx.beginPath(); ctx.fillStyle = '#00d4ff'
      ctx.arc(0, 0, 3, 0, Math.PI * 2); ctx.fill()
      // 前方指示 (小三角)
      ctx.fillStyle = '#00d4ff'; ctx.beginPath()
      ctx.moveTo(0, -S - 4); ctx.lineTo(-3, -S + 1); ctx.lineTo(3, -S + 1); ctx.closePath(); ctx.fill()
      ctx.restore()
      // 高度标签
      ctx.fillStyle = '#fff'; ctx.font = 'bold 10px monospace'
      ctx.fillText('h=' + Math.abs(drone.d).toFixed(0) + 'm', dp.x + pulse + 6, dp.y + 4)

      // 点击标记 (红色十字 + 坐标)
      if (clickPos) {
        const cp = ned2c(clickPos.n, clickPos.e, cx, cy, scale)
        ctx.strokeStyle = '#ff6b6b'; ctx.lineWidth = 1.5
        ctx.beginPath(); ctx.moveTo(cp.x - 10, cp.y); ctx.lineTo(cp.x + 10, cp.y); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(cp.x, cp.y - 10); ctx.lineTo(cp.x, cp.y + 10); ctx.stroke()
        // 虚线圈
        ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(255,107,107,0.5)'
        ctx.beginPath(); ctx.arc(cp.x, cp.y, 15, 0, Math.PI * 2); ctx.stroke()
        ctx.setLineDash([])
        // 坐标文字
        ctx.fillStyle = '#ff6b6b'; ctx.font = '10px monospace'
        ctx.fillText(`(${clickPos.n.toFixed(0)}, ${clickPos.e.toFixed(0)})`, cp.x + 14, cp.y - 8)
        // 与无人机的连线
        ctx.strokeStyle = 'rgba(255,107,107,0.3)'; ctx.lineWidth = 1; ctx.setLineDash([5, 5])
        ctx.beginPath(); ctx.moveTo(dp.x, dp.y); ctx.lineTo(cp.x, cp.y); ctx.stroke()
        ctx.setLineDash([])
        // 距离
        const dist = Math.sqrt((clickPos.n - drone.n) ** 2 + (clickPos.e - drone.e) ** 2)
        const mx = (dp.x + cp.x) / 2, my = (dp.y + cp.y) / 2
        ctx.fillStyle = 'rgba(255,107,107,0.7)'; ctx.font = '9px monospace'
        ctx.fillText(dist.toFixed(0) + 'm', mx + 4, my - 4)
      }

      // 比例尺
      const bl = 50 * scale
      if (bl > 20) {
        ctx.strokeStyle = 'rgba(255,255,255,0.4)'; ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(w - 20 - bl, h - 25); ctx.lineTo(w - 20, h - 25); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(w - 20 - bl, h - 29); ctx.lineTo(w - 20 - bl, h - 21); ctx.stroke()
        ctx.beginPath(); ctx.moveTo(w - 20, h - 29); ctx.lineTo(w - 20, h - 21); ctx.stroke()
        ctx.fillStyle = 'rgba(255,255,255,0.5)'; ctx.font = '9px monospace'; ctx.fillText('50m', w - 20 - bl / 2 - 10, h - 12)
      }

      // HUD 左下
      ctx.fillStyle = 'rgba(255,255,255,0.5)'; ctx.font = '10px monospace'
      ctx.fillText('N:' + drone.n.toFixed(0) + ' E:' + drone.e.toFixed(0) + ' | pts:' + trail.length + ' | lm:' + landmarks.length, 8, h - 10)

      anim.current = requestAnimationFrame(draw)
    }
    anim.current = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(anim.current)
  }, [sz, trail, landmarks, reports, alerts, drone, scale, off, clickPos])

  // 鼠标事件
  const onDown = (e) => {
    if (e.button === 2) return  // 右键不拖拽
    setDrag(true); dRef.current = { x: e.clientX, y: e.clientY, ox: off.x, oy: off.y }
  }
  const onMove = (e) => { if (!drag) return; setOff({ x: dRef.current.ox + e.clientX - dRef.current.x, y: dRef.current.oy + e.clientY - dRef.current.y }) }
  const onUp = (e) => {
    if (drag) {
      const moved = Math.abs(e.clientX - dRef.current.x) + Math.abs(e.clientY - dRef.current.y)
      if (moved < 5) {
        // 点击而非拖拽 → 设置目标点
        const rect = canvasRef.current.getBoundingClientRect()
        const px = e.clientX - rect.left, py = e.clientY - rect.top
        const cx = sz.w / 2 + off.x, cy = sz.h / 2 + off.y
        const ned = c2ned(px, py, cx, cy, scale)
        setClickPos({ px, py, n: ned.n, e: ned.e })
        setShowInput(true)
        setCmdText('')
        setTimeout(() => inputRef.current?.focus(), 50)
      }
    }
    setDrag(false)
  }
  const onWheel = (e) => { e.preventDefault(); setScale(prev => Math.max(0.1, Math.min(10, prev * (e.deltaY < 0 ? 1.15 : 0.87)))) }

  // 发送指令
  const sendCommand = () => {
    if (!clickPos) return
    const coordInfo = `目标坐标: NED (${clickPos.n.toFixed(0)}, ${clickPos.e.toFixed(0)})`
    const fullCmd = cmdText.trim()
      ? `${cmdText.trim()} [${coordInfo}]`
      : `飞到坐标 (${clickPos.n.toFixed(0)}, ${clickPos.e.toFixed(0)}) 附近，到达后观察一下周围环境，然后用 ask_user 问我接下来做什么`
    if (onCommand) onCommand(fullCmd)
    setShowInput(false)
    setClickPos(null)
    setCmdText('')
  }

  const cancelClick = () => {
    setShowInput(false)
    setClickPos(null)
    setCmdText('')
  }

  return (
    <div ref={boxRef} style={{ width: '100%', height: '100%', position: 'relative', borderRadius: 6, overflow: 'hidden', background: '#0a0e17' }}>
      <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block', cursor: drag ? 'grabbing' : 'crosshair' }}
        onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={() => setDrag(false)} onWheel={onWheel}
        onContextMenu={(e) => e.preventDefault()} />

      {/* 图例 */}
      <div style={{ position: 'absolute', top: 8, left: 10, display: 'flex', gap: 10, opacity: 0.8, pointerEvents: 'none' }}>
        <span style={{ fontSize: 10, color: '#00d4ff' }}>{'\u25cf'} 无人机</span>
        <span style={{ fontSize: 10, color: '#ffc832' }}>{'\u25cf'} 地标</span>
        <span style={{ fontSize: 10, color: '#00d4ff' }}>{'\u25b2'} 报告</span>
        <span style={{ fontSize: 10, color: '#ff4444' }}>{'\u26a0'} 警报</span>
        <span style={{ fontSize: 10, color: '#ff6b6b' }}>+ 点击指挥</span>
      </div>

      {/* 工具栏 */}
      <div style={{ position: 'absolute', top: 8, right: 10, display: 'flex', gap: 4 }}>
        <button onClick={() => { setOff({ x: 0, y: 0 }); setScale(1.5) }}
          style={{ fontSize: 10, padding: '3px 8px', background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', borderRadius: 4, cursor: 'pointer' }}>
          重置视图
        </button>
        <button onClick={() => { setTrail([]); setReports([]); setAlerts([]) }}
          style={{ fontSize: 10, padding: '3px 8px', background: 'rgba(0,0,0,0.6)', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', borderRadius: 4, cursor: 'pointer' }}>
          清除轨迹
        </button>
      </div>

      {/* 点击后的指令输入面板 */}
      {showInput && clickPos && (
        <div style={{
          position: 'absolute',
          left: Math.min(clickPos.px + 20, sz.w - 280),
          top: Math.min(clickPos.py - 10, sz.h - 140),
          width: 260,
          background: 'rgba(10,14,23,0.95)',
          border: '1px solid rgba(0,212,255,0.4)',
          borderRadius: 8,
          padding: 12,
          boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
          zIndex: 10,
        }}>
          <div style={{ fontSize: 11, color: '#00d4ff', marginBottom: 6, fontFamily: 'monospace' }}>
            {'\ud83d\udccd'} 目标: ({clickPos.n.toFixed(0)}, {clickPos.e.toFixed(0)}) | 距离: {Math.sqrt((clickPos.n - drone.n) ** 2 + (clickPos.e - drone.e) ** 2).toFixed(0)}m
          </div>
          <input
            ref={inputRef}
            value={cmdText}
            onChange={(e) => setCmdText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') sendCommand(); if (e.key === 'Escape') cancelClick() }}
            placeholder="输入指令... (回车发送，留空=飞过去看看)"
            style={{
              width: '100%', padding: '6px 8px',
              background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(0,212,255,0.3)',
              borderRadius: 4, color: '#e2e8f0', fontSize: 11, outline: 'none',
              fontFamily: 'monospace', boxSizing: 'border-box',
            }}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            <button onClick={sendCommand}
              style={{ flex: 1, padding: '5px 0', background: 'rgba(0,212,255,0.2)', border: '1px solid rgba(0,212,255,0.4)', color: '#00d4ff', borderRadius: 4, fontSize: 10, cursor: 'pointer', fontWeight: 600 }}>
              {'\u2708\ufe0f'} 发送指令
            </button>
            <button onClick={() => { setCmdText('去这个位置多转几圈仔细看看'); }}
              style={{ flex: 1, padding: '5px 0', background: 'rgba(255,200,50,0.15)', border: '1px solid rgba(255,200,50,0.3)', color: '#ffc832', borderRadius: 4, fontSize: 10, cursor: 'pointer' }}>
              {'\ud83d\udd0d'} 仔细查看
            </button>
            <button onClick={cancelClick}
              style={{ padding: '5px 8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.15)', color: '#94a3b8', borderRadius: 4, fontSize: 10, cursor: 'pointer' }}>
              ✕
            </button>
          </div>
          <div style={{ fontSize: 9, color: '#64748b', marginTop: 6 }}>
            提示: 点击其他位置切换目标 | Esc 取消
          </div>
        </div>
      )}
    </div>
  )
}
