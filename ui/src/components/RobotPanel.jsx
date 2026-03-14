/**
 * RobotPanel.jsx — 左侧机器人状态面板
 */
import { useState } from 'react'

const TYPE_ICON = { UAV: '✈️', UGV: '🚗' }
const STATUS_LABEL = { idle: '空闲', executing: '执行中', error: '错误' }

export default function RobotPanel({ worldState, currentRobot, onSelectRobot }) {
  const robots = worldState.robots || {}
  const targets = worldState.targets || []

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 10,
      height: '100%', overflow: 'auto',
    }}>
      {/* 机器人列表 */}
      <div className="card" style={{ padding: 10 }}>
        <div style={{ color: 'var(--text-dim)', fontSize: 10, marginBottom: 8, letterSpacing: 1 }}>
          ▸ 机器人 ({Object.keys(robots).length})
        </div>
        {Object.keys(robots).length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 11, padding: 8 }}>系统初始化中...</div>
        ) : (
          Object.entries(robots).map(([id, data]) => (
            <RobotCard
              key={id}
              id={id}
              data={data}
              selected={id === currentRobot}
              onClick={() => onSelectRobot(id)}
            />
          ))
        )}
      </div>

      {/* 已知目标 */}
      <div className="card" style={{ padding: 10 }}>
        <div style={{ color: 'var(--text-dim)', fontSize: 10, marginBottom: 8, letterSpacing: 1 }}>
          ▸ 已知目标 ({targets.length})
        </div>
        {targets.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>暂无目标</div>
        ) : (
          targets.map((t, i) => <TargetCard key={i} target={t} />)
        )}
      </div>

      {/* 地图简要 */}
      <div className="card" style={{ padding: 10, flex: 1 }}>
        <div style={{ color: 'var(--text-dim)', fontSize: 10, marginBottom: 8, letterSpacing: 1 }}>
          ▸ 态势图 (简化)
        </div>
        <MiniMap robots={robots} targets={targets} currentRobot={currentRobot} />
      </div>
    </div>
  )
}

function RobotCard({ id, data, selected, onClick }) {
  const batteryColor = data.battery > 50 ? 'var(--success)'
    : data.battery > 20 ? 'var(--warning)'
    : 'var(--danger)'

  return (
    <div
      onClick={onClick}
      style={{
        padding: '8px 10px',
        borderRadius: 'var(--radius)',
        border: `1px solid ${selected ? 'var(--accent)' : 'var(--border)'}`,
        background: selected ? 'rgba(0,212,255,.06)' : 'transparent',
        cursor: 'pointer',
        marginBottom: 4,
        transition: 'all .15s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span>{TYPE_ICON[data.robot_type] || '🤖'}</span>
        <span style={{ fontWeight: 600, fontSize: 12, color: selected ? 'var(--accent)' : 'var(--text)' }}>
          {id}
        </span>
        <span className={`badge ${data.robot_type?.toLowerCase()}`} style={{ marginLeft: 'auto' }}>
          {data.robot_type}
        </span>
      </div>

      {/* 状态行 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
        <span className={`badge ${data.status || 'idle'}`}>
          {STATUS_LABEL[data.status] || data.status}
        </span>
        {data.in_air !== undefined && (
          <span style={{
            fontSize: 10,
            color: data.in_air ? 'var(--accent)' : 'var(--text-muted)',
            marginLeft: 2,
          }}>
            {data.in_air ? '✈ 飞行中' : '⬇ 地面'}
          </span>
        )}
      </div>

      {/* 电量 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 10, width: 28 }}>电量</span>
        <div style={{
          flex: 1, height: 4, background: 'var(--bg)',
          borderRadius: 2, overflow: 'hidden',
        }}>
          <div style={{
            width: `${Math.max(0, Math.min(100, data.battery || 0))}%`,
            height: '100%',
            background: batteryColor,
            transition: 'width .3s',
            borderRadius: 2,
          }} />
        </div>
        <span style={{ color: batteryColor, fontSize: 10, width: 30 }}>
          {(data.battery || 0).toFixed(0)}%
        </span>
      </div>

      {/* 位置（遥测实时更新） */}
      {data.position && (
        <div style={{ color: 'var(--text-dim)', fontSize: 10, marginTop: 4, letterSpacing: 0 }}>
          <span style={{ color: 'var(--text-muted)' }}>N </span>{data.position[0]?.toFixed(1)}m
          <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>E </span>{data.position[1]?.toFixed(1)}m
          <span style={{ color: 'var(--text-muted)', marginLeft: 6 }}>↑ </span>{data.position[2]?.toFixed(1)}m
        </div>
      )}
    </div>
  )
}

function TargetCard({ target }) {
  return (
    <div style={{
      padding: '6px 8px',
      borderRadius: 'var(--radius)',
      border: '1px solid var(--border)',
      marginBottom: 4,
      fontSize: 11,
    }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <span>🎯</span>
        <span style={{ fontWeight: 600 }}>{target.label}</span>
        <span style={{
          marginLeft: 'auto',
          color: target.confidence > 0.8 ? 'var(--success)' : 'var(--warning)',
          fontSize: 10,
        }}>
          {(target.confidence * 100).toFixed(0)}%
        </span>
      </div>
      <div style={{ color: 'var(--text-dim)', fontSize: 10, marginTop: 2 }}>
        [{(target.position || [0,0,0]).map(v => v.toFixed(0)).join(', ')}]
        <span style={{ marginLeft: 6, color: 'var(--text-muted)' }}>{target.target_id}</span>
      </div>
    </div>
  )
}

function MiniMap({ robots, targets, currentRobot }) {
  // 简化的 SVG 态势图，100x100 坐标空间
  const W = 200, H = 160
  const scale = (v, max = 400) => (v / max) * (W - 20) + 10

  const robotEntries = Object.entries(robots)

  return (
    <svg
      width="100%" viewBox={`0 0 ${W} ${H}`}
      style={{ background: 'var(--bg)', borderRadius: 4, border: '1px solid var(--border)' }}
    >
      {/* 网格 */}
      {[1,2,3].map(i => (
        <g key={i}>
          <line
            x1={W * i / 4} y1={0} x2={W * i / 4} y2={H}
            stroke="var(--border)" strokeWidth={0.5}
          />
          <line
            x1={0} y1={H * i / 4} x2={W} y2={H * i / 4}
            stroke="var(--border)" strokeWidth={0.5}
          />
        </g>
      ))}

      {/* 目标 */}
      {targets.map((t, i) => {
        const x = scale(t.position?.[0] || 0)
        const y = H - scale(t.position?.[1] || 0, 300) - 10
        return (
          <g key={i}>
            <circle cx={x} cy={y} r={5} fill="none" stroke="var(--warning)" strokeWidth={1.5} />
            <circle cx={x} cy={y} r={2} fill="var(--warning)" />
            <text x={x + 7} y={y + 4} fontSize={7} fill="var(--warning)" fontFamily="var(--font)">
              {t.label}
            </text>
          </g>
        )
      })}

      {/* 机器人 */}
      {robotEntries.map(([id, data]) => {
        const x = scale(data.position?.[0] || 0)
        const y = H - scale(data.position?.[1] || 0, 300) - 10
        const isSelected = id === currentRobot
        const color = data.robot_type === 'UAV' ? 'var(--accent)' : '#a78bfa'
        const statusColor = data.status === 'executing' ? 'var(--warning)'
          : data.status === 'error' ? 'var(--danger)' : color

        return (
          <g key={id}>
            {isSelected && (
              <circle cx={x} cy={y} r={10} fill="none" stroke={color} strokeWidth={0.8} strokeDasharray="2 2">
                <animateTransform attributeName="transform" type="rotate"
                  from={`0 ${x} ${y}`} to={`360 ${x} ${y}`} dur="4s" repeatCount="indefinite" />
              </circle>
            )}
            <circle cx={x} cy={y} r={5} fill={statusColor} opacity={0.9} />
            <text x={x + 7} y={y - 3} fontSize={8} fill={color} fontFamily="var(--font)" fontWeight={isSelected ? 'bold' : 'normal'}>
              {id}
            </text>
          </g>
        )
      })}

      {/* 图例 */}
      <text x={4} y={H - 3} fontSize={7} fill="var(--text-dim)" fontFamily="var(--font)">
        态势简图 (NED坐标投影)
      </text>
    </svg>
  )
}
