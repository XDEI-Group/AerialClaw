/**
 * SkillPanel.jsx — 中间技能控制面板（手动模式核心）
 *
 * 技能按选中机器人的 robot_type 过滤：
 *   - 只展示 skill.robot_type 包含当前机器人类型的技能
 *   - UAV 选中 → 只显示 UAV 技能；UGV 选中 → 只显示 UGV 技能
 *   - 支持按技能分类（全部 / 硬技能 / 软技能 / 感知技能）二级过滤
 */
import { useState, useCallback } from 'react'

// 技能类型颜色
const TYPE_COLORS = {
  hard:       { bg: 'rgba(245,158,11,.08)', border: 'rgba(245,158,11,.3)', text: '#fbbf24', accent: '#f59e0b' },
  soft:       { bg: 'rgba(34,197,94,.08)',  border: 'rgba(34,197,94,.3)',  text: '#4ade80', accent: '#22c55e' },
  perception: { bg: 'rgba(0,212,255,.06)',  border: 'rgba(0,212,255,.2)',  text: '#67e8f9', accent: '#00d4ff' },
}

// 技能默认参数
const SKILL_PARAMS = {
  // 硬技能 — UAV
  takeoff:          { altitude: 5.0 },
  land:             {},
  fly_to:           { target_position: [10, 0, -5], speed: 2.0 },
  hover:            { duration: 5.0 },
  get_position:     {},
  get_battery:      {},
  return_to_launch: {},
  change_altitude:  { altitude: 10.0 },
  // 硬技能 — UGV
  move_to:          { target_position: [10, 0, 0], speed: 1.0 },
  // 硬技能 — UAV+UGV
  scan_lidar:       { scan_range: 20.0 },
  capture_image:    { camera_type: 'rgb' },
  // 软技能
  search_target:    { area_position: [50, 0, -20], scan_range: 30.0 },
  rescue_person:    { target_position: [120, 80, -15], rescue_position: [120, 80] },
  patrol_area:      { waypoints: [[0,0,-10],[20,0,-10],[20,20,-10],[0,20,-10]], scan_range: 25.0 },
  // 感知技能
  detect_object:    { target_label: 'person' },
  recognize_speech: {},
  fuse_perception:  {},
  scan_area:        { center: [0, 0, -20], radius: 50.0 },
  get_sensor_data:  { sensor_type: 'all' },
}

// 技能图标
const SKILL_ICONS = {
  takeoff:          '🚀',
  land:             '🛬',
  fly_to:           '✈️',
  hover:            '🔄',
  get_position:     '📍',
  get_battery:      '🔋',
  return_to_launch: '🏠',
  change_altitude:  '⬆️',
  move_to:          '🚗',
  scan_lidar:       '📡',
  capture_image:    '📷',
  search_target:    '🔍',
  rescue_person:    '🚑',
  patrol_area:      '🗺️',
  detect_object:    '👁️',
  recognize_speech: '🎤',
  fuse_perception:  '🧠',
  scan_area:        '🌐',
  get_sensor_data:  '📡',
}

const SKILL_LABELS = {
  takeoff:          '起飞',
  land:             '降落',
  fly_to:           '飞行到',
  hover:            '悬停',
  get_position:     '获取位置',
  get_battery:      '检查电量',
  return_to_launch: '返航',
  change_altitude:  '调整高度',
  move_to:          '移动到',
  scan_lidar:       'LiDAR扫描',
  capture_image:    '拍照',
  search_target:    '搜索目标',
  rescue_person:    '救援',
  patrol_area:      '巡逻',
  detect_object:    '目标检测',
  recognize_speech: '语音识别',
  fuse_perception:  '融合感知',
  scan_area:        '区域扫描',
  get_sensor_data:  '传感器数据',
}

// 分类 tab 定义
const FILTER_TABS = [
  { key: 'all',        label: '全部' },
  { key: 'hard',       label: '硬技能' },
  { key: 'soft',       label: '软技能' },
  { key: 'perception', label: '感知技能' },
]

export default function SkillPanel({
  skillCatalog,
  currentRobot,
  worldState,
  isExecuting,
  onExecuteSkill,
  lastResult,
}) {
  const [selectedSkill, setSelectedSkill] = useState(null)
  const [params, setParams] = useState({})
  const [activeFilter, setActiveFilter] = useState('all')

  // 当前机器人类型（后端返回 robot_type 字段，默认 UAV）
  const currentRobotType = worldState.robots?.[currentRobot]?.robot_type || 'UAV'

  // 取出当前机器人的技能列表（服务端已按 robot_type 隔离，无需再做 robot_type 过滤）
  // skillCatalog 格式: { robot_id: [skills] }
  const robotSkills = (skillCatalog[currentRobot] || [])

  // skill_type 过滤（tab 切换）
  const filtered = activeFilter === 'all'
    ? robotSkills
    : robotSkills.filter(s => s.skill_type === activeFilter)

  // 每个 tab 的数量徽标
  const byType = (type) => type === 'all'
    ? robotSkills.length
    : robotSkills.filter(s => s.skill_type === type).length

  // 选中技能
  const handleSelectSkill = useCallback((skill) => {
    setSelectedSkill(skill)
    setParams({ ...(SKILL_PARAMS[skill.name] || {}) })
  }, [])

  // 执行技能
  const handleExecute = useCallback(() => {
    if (!selectedSkill || isExecuting) return
    onExecuteSkill(currentRobot, selectedSkill.name, params)
  }, [selectedSkill, params, currentRobot, isExecuting, onExecuteSkill])

  const robotStatus = worldState.robots?.[currentRobot]?.status || 'idle'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%', overflow: 'hidden' }}>

      {/* 当前选中机器人 */}
      <div className="card" style={{ padding: '8px 12px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 16 }}>{currentRobotType === 'UAV' ? '✈️' : '🚗'}</span>
          <span style={{ fontWeight: 600, color: 'var(--accent)' }}>{currentRobot}</span>
          <span className={`badge ${robotStatus}`}>
            {robotStatus === 'idle' ? '空闲' : robotStatus === 'executing' ? '执行中' : robotStatus === 'airborne' ? '飞行中' : robotStatus}
          </span>
          <span className={`badge ${currentRobotType?.toLowerCase()}`}>{currentRobotType}</span>
          <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 11 }}>
            电量: {(worldState.robots?.[currentRobot]?.battery || 0).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* 技能分类过滤 tabs */}
      <div style={{ display: 'flex', gap: 4, flexShrink: 0, alignItems: 'center', flexWrap: 'wrap' }}>
        {FILTER_TABS.map(tab => {
          const count = byType(tab.key)
          const isActive = activeFilter === tab.key
          return (
            <button
              key={tab.key}
              onClick={() => setActiveFilter(tab.key)}
              style={{
                padding: '3px 10px',
                borderRadius: 99,
                border: `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
                background: isActive ? 'rgba(0,212,255,.12)' : 'transparent',
                color: isActive ? 'var(--accent)' : 'var(--text-dim)',
                fontSize: 10,
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 4,
              }}
            >
              {tab.label}
              <span style={{
                background: isActive ? 'rgba(0,212,255,.2)' : 'rgba(255,255,255,.06)',
                borderRadius: 99,
                padding: '0 5px',
                fontSize: 9,
              }}>{count}</span>
            </button>
          )
        })}
        <span style={{ flex: 1 }} />
        <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>
          点击卡片 → 编辑参数 → 执行
        </span>
      </div>

      {/* 技能网格 */}
      <div style={{
        flex: 1, overflowY: 'auto',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))',
        gap: 6,
        alignContent: 'start',
      }}>
        {filtered.length === 0 && (
          <div style={{
            gridColumn: '1 / -1',
            textAlign: 'center',
            color: 'var(--text-muted)',
            fontSize: 12,
            padding: 20,
          }}>
            当前机器人（{currentRobotType}）暂无可用技能
          </div>
        )}
        {filtered.map(skill => {
          const tc = TYPE_COLORS[skill.skill_type] || TYPE_COLORS.hard
          const isSelected = selectedSkill?.name === skill.name
          const statusColor = skill.last_execution_status === 'success' ? 'var(--success)'
            : skill.last_execution_status === 'failed' ? 'var(--danger)'
            : 'var(--text-muted)'

          return (
            <div
              key={skill.name}
              onClick={() => handleSelectSkill(skill)}
              style={{
                padding: '10px 8px',
                borderRadius: 'var(--radius)',
                border: `1px solid ${isSelected ? tc.accent : tc.border}`,
                background: isSelected ? tc.bg : 'var(--bg-card)',
                cursor: 'pointer',
                transition: 'all .15s',
                boxShadow: isSelected ? `0 0 8px ${tc.accent}44` : 'none',
                display: 'flex', flexDirection: 'column', gap: 4,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ fontSize: 16 }}>{SKILL_ICONS[skill.name] || '⚙️'}</span>
                <span className={`badge ${skill.skill_type}`} style={{ fontSize: 9 }}>
                  {skill.skill_type === 'hard' ? '硬' : skill.skill_type === 'soft' ? '软' : '感知'}
                </span>
              </div>
              <div style={{ fontWeight: 600, fontSize: 12, color: isSelected ? tc.text : 'var(--text)' }}>
                {SKILL_LABELS[skill.name] || skill.name}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-dim)', lineHeight: 1.4 }}>
                {skill.description?.slice(0, 40)}...
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: statusColor }} />
                <span style={{ color: statusColor, fontSize: 9 }}>
                  {skill.last_execution_status === 'never' ? '未执行'
                    : skill.last_execution_status === 'success' ? '上次成功'
                    : '上次失败'}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* 参数编辑 + 执行区 */}
      {selectedSkill && (
        <div className="card" style={{ flexShrink: 0, padding: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 18 }}>{SKILL_ICONS[selectedSkill.name] || '⚙️'}</span>
            <span style={{ fontWeight: 700, color: 'var(--accent)' }}>
              {SKILL_LABELS[selectedSkill.name] || selectedSkill.name}
            </span>
            <span className={`badge ${selectedSkill.skill_type}`}>{selectedSkill.skill_type}</span>
          </div>

          <ParamEditor
            skill={selectedSkill}
            params={params}
            onChange={setParams}
          />

          <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
            <button
              className="btn primary"
              onClick={handleExecute}
              disabled={isExecuting}
              style={{ flex: 1 }}
            >
              {isExecuting ? '⏳ 执行中...' : `▶ 执行 [${currentRobot}]`}
            </button>
            <button className="btn" onClick={() => setSelectedSkill(null)} style={{ padding: '6px 10px' }}>
              ✕
            </button>
          </div>
        </div>
      )}

      {/* 上次执行结果 */}
      {lastResult && (
        <SkillResultCard result={lastResult} />
      )}
    </div>
  )
}

// ── 参数编辑器 ───────────────────────────────────────────────────────────────

function ParamEditor({ skill, params, onChange }) {
  const schema = skill.input_schema || {}
  const entries = Object.entries(schema)

  if (entries.length === 0) {
    return (
      <div style={{ color: 'var(--text-dim)', fontSize: 11, padding: '4px 0' }}>
        该技能无需输入参数
      </div>
    )
  }

  const updateParam = (key, rawValue) => {
    let value = rawValue
    // 尝试解析 JSON（数组/数字）
    try {
      const parsed = JSON.parse(rawValue)
      value = parsed
    } catch {
      // 保持字符串
    }
    onChange(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {entries.map(([key, desc]) => {
        const val = params[key]
        const displayVal = val === undefined ? '' : (typeof val === 'object' ? JSON.stringify(val) : String(val))
        return (
          <div key={key}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
              <span style={{ color: 'var(--accent)', fontSize: 11, fontWeight: 600 }}>{key}</span>
              <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>{String(desc).slice(0, 30)}</span>
            </div>
            <input
              value={displayVal}
              onChange={e => updateParam(key, e.target.value)}
              placeholder={String(desc).slice(0, 50)}
              style={{ fontSize: 11 }}
            />
          </div>
        )
      })}
    </div>
  )
}

// ── 执行结果卡片 ──────────────────────────────────────────────────────────────

function SkillResultCard({ result }) {
  const ok = result.ok
  return (
    <div style={{
      padding: 10,
      borderRadius: 'var(--radius)',
      border: `1px solid ${ok ? 'rgba(34,197,94,.3)' : 'rgba(239,68,68,.3)'}`,
      background: ok ? 'rgba(34,197,94,.05)' : 'rgba(239,68,68,.05)',
      flexShrink: 0,
      animation: 'fadeIn .2s ease',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <span>{ok ? '✅' : '❌'}</span>
        <span style={{ fontWeight: 600, color: ok ? 'var(--success)' : 'var(--danger)', fontSize: 12 }}>
          {ok ? '执行成功' : '执行失败'}
        </span>
        <span style={{ color: 'var(--text-dim)', fontSize: 10, marginLeft: 'auto' }}>
          [{result.robot}] {result.skill} · {result.cost_time?.toFixed(2)}s
        </span>
      </div>
      {ok && result.output && Object.keys(result.output).length > 0 && (
        <div style={{ color: 'var(--text-dim)', fontSize: 10, fontFamily: 'monospace' }}>
          {Object.entries(result.output).map(([k, v]) => (
            <div key={k}>
              <span style={{ color: 'var(--accent)' }}>{k}</span>: {JSON.stringify(v)}
            </div>
          ))}
        </div>
      )}
      {!ok && result.error && (
        <div style={{ color: 'var(--danger)', fontSize: 11 }}>{result.error}</div>
      )}
    </div>
  )
}
