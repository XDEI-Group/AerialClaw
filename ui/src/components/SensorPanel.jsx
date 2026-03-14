/**
 * SensorPanel.jsx — 传感器数据可视化面板
 *
 * 包含：
 *   1. 4× RGB 摄像头 (front/rear/left/right) 2×2 网格
 *   2. 2D 激光雷达俯视扫描图（Canvas 绘制）
 */
import { useEffect, useRef, useState, useCallback } from 'react'

const CAM_LABELS = {
  front: '▲ 前',
  rear:  '▼ 后',
  left:  '◀ 左',
  right: '▶ 右',
  down:  '⊙ 下',
}

// ── 单个摄像头视图 ─────────────────────────────────────────────────────────

function CameraCell({ data, label }) {
  if (!data || !data.image) {
    return (
      <div style={{
        height: 80, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#111', borderRadius: 4, color: 'var(--text-muted)', fontSize: 10,
      }}>
        {label} 📷...
      </div>
    )
  }

  return (
    <div style={{ position: 'relative' }}>
      <img
        src={`data:image/jpeg;base64,${data.image}`}
        alt={label}
        style={{
          width: '100%', height: 80, objectFit: 'cover',
          borderRadius: 4, display: 'block',
        }}
      />
      <div style={{
        position: 'absolute', top: 2, left: 3,
        fontSize: 9, color: '#0f0', fontFamily: 'monospace',
        background: 'rgba(0,0,0,0.6)', padding: '1px 4px', borderRadius: 2,
      }}>
        {label}
      </div>
      <div style={{
        position: 'absolute', bottom: 1, right: 3,
        fontSize: 8, color: '#0f0', fontFamily: 'monospace',
        background: 'rgba(0,0,0,0.5)', padding: '1px 3px', borderRadius: 2,
      }}>
        {data.fps}fps
      </div>
    </div>
  )
}

// ── 4 相机 2×2 网格 ──────────────────────────────────────────────────────

function CameraGrid({ sensorCameras, onClickCamera }) {
  // 布局: front | down  | rear
  //        left  | right
  const layout = [
    ['front', 'down', 'rear'],
    ['left', 'right'],
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {layout.map((row, ri) => (
        <div key={ri} style={{ display: 'flex', gap: 3 }}>
          {row.map(dir => (
            <div key={dir} style={{ flex: 1, cursor: 'pointer' }}
              onClick={(e) => { e.stopPropagation(); onClickCamera?.(dir) }}>
              <CameraCell
                data={sensorCameras?.[dir]}
                label={CAM_LABELS[dir]}
              />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}


// ── 激光雷达扫描图 ────────────────────────────────────────────────────────────

function LidarView({ sensorLidar }) {
  const canvasRef = useRef(null)
  const [maxRange, setMaxRange] = useState(30)

  const drawLidar = useCallback((data) => {
    const canvas = canvasRef.current
    if (!canvas || !data) return

    const ctx = canvas.getContext('2d')
    const W = canvas.width
    const H = canvas.height
    const cx = W / 2
    const cy = H / 2
    const scale = (Math.min(W, H) / 2 - 10) / maxRange

    // 清屏
    ctx.fillStyle = '#0a0a0a'
    ctx.fillRect(0, 0, W, H)

    // 网格（同心圆）
    ctx.strokeStyle = '#1a1a2e'
    ctx.lineWidth = 0.5
    for (let r = 5; r <= maxRange; r += 5) {
      ctx.beginPath()
      ctx.arc(cx, cy, r * scale, 0, Math.PI * 2)
      ctx.stroke()
    }
    // 十字线
    ctx.beginPath()
    ctx.moveTo(cx, 0); ctx.lineTo(cx, H)
    ctx.moveTo(0, cy); ctx.lineTo(W, cy)
    ctx.stroke()

    // 比例尺标注
    ctx.fillStyle = '#444'
    ctx.font = '9px monospace'
    ctx.fillText(`${maxRange}m`, cx + 3, 12)
    ctx.fillText(`${Math.round(maxRange / 2)}m`, cx + maxRange / 2 * scale + 3, cy - 3)

    // 雷达点
    const is3d = data.is_3d && data.layers
    let minDist = Infinity
    let obstacleCount = 0

    if (is3d) {
      // 3D 点云: 多层渲染
      const layers = data.layers
      const vCount = layers.length
      const hCount = layers[0]?.length || 0
      const hStep = (data.angle_max - data.angle_min) / hCount

      for (let vi = 0; vi < vCount; vi++) {
        const layer = layers[vi]
        const t = vCount <= 1 ? 0.5 : vi / (vCount - 1)
        for (let hi = 0; hi < layer.length; hi++) {
          const r = layer[hi]
          if (r <= data.range_min || r >= data.range_max || !isFinite(r)) continue

          const angle = data.angle_min + hi * hStep
          const px = cx + r * Math.sin(-angle) * scale
          const py = cy - r * Math.cos(angle) * scale

          // 颜色: 低层蓝绿 → 中层绿 → 高层橙红
          const red = Math.round(34 + t * 220)
          const green = Math.round(200 - t * 120)
          const blue = Math.round(100 - t * 60)
          ctx.fillStyle = `rgb(${red},${green},${blue})`
          ctx.fillRect(px - 1, py - 1, 2, 2)

          if (r < minDist) minDist = r
          if (r < data.range_max * 0.8) obstacleCount++
        }
      }

      // 3D 标记
      ctx.fillStyle = '#666'; ctx.font = '9px monospace'
      ctx.fillText(`3D ${vCount}L`, 4, 12)
    } else {
      // 2D 兼容
      const { ranges, angle_min, angle_increment, range_min, range_max } = data
      for (let i = 0; i < ranges.length; i++) {
        const r = ranges[i]
        if (r <= range_min || r > range_max || !isFinite(r)) continue

        const angle = angle_min + i * angle_increment
        const px = cx + r * Math.sin(-angle) * scale
        const py = cy - r * Math.cos(angle) * scale

        const ratio = Math.min(r / maxRange, 1)
        const red = Math.round(255 * (1 - ratio))
        const green = Math.round(255 * ratio)
        ctx.fillStyle = `rgb(${red},${green},50)`
        ctx.fillRect(px - 1, py - 1, 2, 2)

        if (r < minDist) minDist = r
        if (r < range_max * 0.8) obstacleCount++
      }
    }

    // 无人机位置（中心红点）
    ctx.fillStyle = '#ff3333'
    ctx.beginPath()
    ctx.arc(cx, cy, 4, 0, Math.PI * 2)
    ctx.fill()

    // 方向箭头（前方）
    ctx.strokeStyle = '#ff3333'
    ctx.lineWidth = 1.5
    ctx.beginPath()
    ctx.moveTo(cx, cy - 6)
    ctx.lineTo(cx, cy - 18)
    ctx.moveTo(cx - 4, cy - 14)
    ctx.lineTo(cx, cy - 18)
    ctx.lineTo(cx + 4, cy - 14)
    ctx.stroke()

    // 信息标注
    ctx.fillStyle = '#888'
    ctx.font = '10px monospace'
    const infoY = H - 6
    ctx.fillText(`最近: ${minDist === Infinity ? '--' : minDist.toFixed(1) + 'm'}`, 4, infoY)
    ctx.fillText(`障碍: ${obstacleCount}`, W - 60, infoY)

  }, [maxRange])

  useEffect(() => {
    drawLidar(sensorLidar)
  }, [sensorLidar, drawLidar])

  if (!sensorLidar) {
    return (
      <div style={{
        height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: '#111', borderRadius: 6, color: 'var(--text-muted)', fontSize: 12,
      }}>
        🔴 等待激光雷达数据...
      </div>
    )
  }

  return (
    <div>
      <canvas
        ref={canvasRef}
        width={280}
        height={280}
        style={{ width: '100%', borderRadius: 6, display: 'block' }}
      />
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, marginTop: 4,
        fontSize: 10, color: 'var(--text-muted)',
      }}>
        <span>范围:</span>
        {[15, 30, 50].map(r => (
          <button
            key={r}
            onClick={() => setMaxRange(r)}
            style={{
              background: maxRange === r ? 'var(--accent)' : 'var(--bg)',
              color: maxRange === r ? '#fff' : 'var(--text-muted)',
              border: '1px solid var(--border)',
              borderRadius: 3, padding: '1px 6px', fontSize: 10, cursor: 'pointer',
            }}
          >
            {r}m
          </button>
        ))}
        <span style={{ marginLeft: 'auto' }}>{sensorLidar.count} 点</span>
      </div>
    </div>
  )
}


// ── 主面板 ────────────────────────────────────────────────────────────────────

export default function SensorPanel({ sensorCamera, sensorCameras, sensorLidar, onOpenCockpit }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%', overflow: 'auto' }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', padding: '2px 0' }}>
        📡 传感器
      </div>

      {/* 5 摄像头网格 — 点击单个进入对应视角驾驶舱 */}
      <div
        style={{ position: 'relative' }}
      >
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3, display: 'flex', justifyContent: 'space-between' }}>
          <span>📷 5× 摄像头</span>
          <span style={{ color: 'var(--accent)', fontSize: 9 }}>🕹️ 点击进入驾驶舱</span>
        </div>
        <CameraGrid sensorCameras={sensorCameras} onClickCamera={onOpenCockpit} />
      </div>

      {/* 激光雷达 */}
      <div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3 }}>
          🔴 2D 激光雷达 (Lidar)
        </div>
        <LidarView sensorLidar={sensorLidar} />
      </div>
    </div>
  )
}
