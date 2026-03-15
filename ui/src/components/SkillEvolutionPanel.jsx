/**
 * SkillEvolutionPanel.jsx — 技能进化面板
 * Props: { socket, connected }
 */
import { useState, useEffect, useCallback } from 'react'

const S = {
  panel: {
    display: 'flex', flexDirection: 'column', gap: 10,
    height: '100%', overflow: 'hidden',
    color: '#e2e8f0', fontSize: 13,
  },
  sectionTitle: {
    fontSize: 11, fontWeight: 700, color: '#00d4ff',
    textTransform: 'uppercase', letterSpacing: '0.06em',
    marginBottom: 8,
  },
  card: {
    background: 'rgba(15,23,42,.7)',
    border: '1px solid rgba(0,212,255,.15)',
    borderRadius: 8,
    padding: 12,
  },
  btn: (color = '#00d4ff') => ({
    background: `rgba(${hexToRgb(color)},.1)`,
    border: `1px solid rgba(${hexToRgb(color)},.45)`,
    borderRadius: 6,
    color, fontSize: 11, fontWeight: 600,
    padding: '5px 12px', cursor: 'pointer',
  }),
  btnSm: {
    background: 'rgba(255,255,255,.04)',
    border: '1px solid rgba(255,255,255,.1)',
    borderRadius: 5,
    color: '#94a3b8', fontSize: 10,
    padding: '3px 8px', cursor: 'pointer',
  },
  btnSmDanger: {
    background: 'rgba(239,68,68,.08)',
    border: '1px solid rgba(239,68,68,.35)',
    borderRadius: 5,
    color: '#f87171', fontSize: 10,
    padding: '3px 8px', cursor: 'pointer',
  },
  emptyMsg: {
    textAlign: 'center', color: '#475569', fontSize: 12, padding: '14px 0',
  },
  toast: (ok) => ({
    position: 'fixed', bottom: 20, right: 20, zIndex: 9999,
    padding: '8px 16px', borderRadius: 8,
    background: ok ? 'rgba(34,197,94,.15)' : 'rgba(239,68,68,.15)',
    border: `1px solid ${ok ? 'rgba(34,197,94,.5)' : 'rgba(239,68,68,.5)'}`,
    color: ok ? '#4ade80' : '#f87171',
    fontSize: 12, fontWeight: 600,
  }),
  pre: {
    background: 'rgba(0,0,0,.3)',
    border: '1px solid rgba(0,212,255,.1)',
    borderRadius: 6, padding: 8,
    fontSize: 10, color: '#94a3b8',
    maxHeight: 120, overflowY: 'auto',
    whiteSpace: 'pre-wrap', wordBreak: 'break-all',
    fontFamily: 'monospace',
  },
}

function hexToRgb(hex) {
  // 只处理常用颜色
  const map = {
    '#00d4ff': '0,212,255',
    '#f59e0b': '245,158,11',
    '#22c55e': '34,197,94',
    '#ef4444': '239,68,68',
    '#a855f7': '168,85,247',
  }
  return map[hex] || '148,163,184'
}

function rateColor(rate) {
  if (rate >= 80) return '#22c55e'
  if (rate >= 50) return '#f59e0b'
  return '#ef4444'
}

function Toast({ msg, ok }) {
  if (!msg) return null
  return <div style={S.toast(ok)}>{msg}</div>
}

// ── 柱状图行 ───────────────────────────────────────────────────────────────────
function BarRow({ name, successRate, avgCost, total }) {
  const pct   = Math.min(100, Math.max(0, successRate))
  const color = rateColor(pct)
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
        <span style={{ fontSize: 12, color: '#e2e8f0', fontWeight: 600 }}>{name}</span>
        <div style={{ display: 'flex', gap: 10, fontSize: 10, color: '#94a3b8' }}>
          <span style={{ color }}>{pct.toFixed(1)}%</span>
          <span>avg {avgCost?.toFixed ? avgCost.toFixed(2) : '—'}s</span>
          <span>×{total ?? 0}</span>
        </div>
      </div>
      {/* 轨道 */}
      <div style={{
        height: 6, borderRadius: 99,
        background: 'rgba(255,255,255,.06)',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          borderRadius: 99,
          background: `linear-gradient(90deg, ${color}cc, ${color})`,
          transition: 'width .4s ease',
          boxShadow: `0 0 6px ${color}66`,
        }} />
      </div>
    </div>
  )
}

// ── 软技能行 ───────────────────────────────────────────────────────────────────
function SoftSkillRow({ skill, onView, onDelete }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '7px 10px',
      background: 'rgba(168,85,247,.06)',
      border: '1px solid rgba(168,85,247,.2)',
      borderRadius: 7,
      marginBottom: 6,
    }}>
      <span style={{ fontSize: 14 }}>🧩</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 12, color: '#c084fc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {skill.name || skill.skill_id}
        </div>
        {skill.description && (
          <div style={{ fontSize: 10, color: '#64748b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {skill.description}
          </div>
        )}
      </div>
      <button style={S.btnSm} onClick={() => onView(skill)}>查看</button>
      <button style={S.btnSmDanger} onClick={() => onDelete(skill.name || skill.skill_id)}>删除</button>
    </div>
  )
}

// ── 主组件 ─────────────────────────────────────────────────────────────────────
export default function SkillEvolutionPanel({ socket, connected }) {
  const [stats,      setStats]      = useState([])   // execution_stats 数组
  const [softSkills, setSoftSkills] = useState([])
  const [loading,    setLoading]    = useState(false)
  const [opLoading,  setOpLoading]  = useState('')   // 'patterns'|'generate'|'retire'
  const [opResult,   setOpResult]   = useState(null) // { title, data }
  const [viewSkill,  setViewSkill]  = useState(null) // 查看详情的软技能
  const [toast,      setToast]      = useState(null)

  const showToast = (msg, ok = true) => {
    setToast({ msg, ok })
    setTimeout(() => setToast(null), 3500)
  }

  // ── 获取技能统计 ────────────────────────────────────────────────────────────
  const fetchStats = useCallback(async () => {
    try {
      const res  = await fetch('/api/skills')
      const data = await res.json()
      // data 可能是 { skills: [...] } 或直接 [...]
      const list = Array.isArray(data) ? data : (data.skills || [])
      // 提取 execution_stats
      const parsed = list.map(s => {
        const es = s.execution_stats || s
        return {
          name:        s.name || s.skill_id || '?',
          successRate: (es.success_rate ?? es.successRate ?? 0),
          avgCost:     (es.avg_cost_time ?? es.avg_cost ?? 0),
          total:       (es.total_executions ?? es.total ?? 0),
        }
      }).filter(s => s.total > 0 || true)
      setStats(parsed)
    } catch (e) {
      showToast('获取技能统计失败: ' + e.message, false)
    }
  }, [])

  // ── 获取软技能列表 ──────────────────────────────────────────────────────────
  const fetchSoftSkills = useCallback(async () => {
    setLoading(true)
    try {
      const res  = await fetch('/api/skills/soft')
      const data = await res.json()
      setSoftSkills(Array.isArray(data) ? data : (data.skills || []))
    } catch (e) {
      showToast('获取软技能失败: ' + e.message, false)
    } finally {
      setLoading(false)
    }
  }, [])

  // ── WebSocket 监听 skill_catalog ────────────────────────────────────────────
  useEffect(() => {
    if (!socket) return
    const handler = (catalog) => {
      // catalog: { robot_id: [skills] } 或直接 execution_stats
      const allSkills = Object.values(catalog).flat()
      const parsed = allSkills
        .filter(s => s.execution_stats)
        .map(s => ({
          name:        s.name,
          successRate: s.execution_stats.success_rate ?? 0,
          avgCost:     s.execution_stats.avg_cost_time ?? 0,
          total:       s.execution_stats.total_executions ?? 0,
        }))
      if (parsed.length) setStats(parsed)
    }
    socket.on('skill_catalog', handler)
    return () => socket.off('skill_catalog', handler)
  }, [socket])

  useEffect(() => {
    fetchStats()
    fetchSoftSkills()
  }, [fetchStats, fetchSoftSkills])

  // ── 软技能删除 ──────────────────────────────────────────────────────────────
  const handleDeleteSoft = async (skillId) => {
    try {
      const res  = await fetch(`/api/skills/soft/${encodeURIComponent(skillId)}`, { method: 'DELETE' })
      const data = await res.json()
      if (res.ok) {
        showToast(`软技能 ${skillId} 已删除`, true)
        fetchSoftSkills()
      } else {
        showToast(data.error || '删除失败', false)
      }
    } catch (e) {
      showToast('删除请求失败: ' + e.message, false)
    }
  }

  // ── 三个操作按钮 ────────────────────────────────────────────────────────────
  const handlePatterns = async () => {
    setOpLoading('patterns')
    setOpResult(null)
    try {
      const res  = await fetch('/api/skills/soft/patterns')
      const data = await res.json()
      setOpResult({ title: '检测到的模式', data })
      showToast('模式检测完成', true)
    } catch (e) {
      showToast('检测失败: ' + e.message, false)
    } finally {
      setOpLoading('')
    }
  }

  const handleGenerate = async () => {
    setOpLoading('generate')
    setOpResult(null)
    try {
      const res  = await fetch('/api/skills/soft/generate', { method: 'POST' })
      const data = await res.json()
      setOpResult({ title: 'AI 生成结果', data })
      showToast('AI 生成完成', true)
      fetchSoftSkills()
    } catch (e) {
      showToast('AI 生成失败: ' + e.message, false)
    } finally {
      setOpLoading('')
    }
  }

  const handleRetire = async () => {
    setOpLoading('retire')
    setOpResult(null)
    try {
      const res  = await fetch('/api/skills/soft/retire', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: true }),
      })
      const data = await res.json()
      setOpResult({ title: '淘汰检查（dry_run）', data })
      showToast('淘汰检查完成', true)
    } catch (e) {
      showToast('淘汰检查失败: ' + e.message, false)
    } finally {
      setOpLoading('')
    }
  }

  // ── 技能统计排序：成功率降序 ────────────────────────────────────────────────
  const sortedStats = [...stats].sort((a, b) => b.successRate - a.successRate)

  // ── UI ──────────────────────────────────────────────────────────────────────
  return (
    <div style={S.panel}>
      <Toast msg={toast?.msg} ok={toast?.ok} />

      {/* 连接状态 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: connected ? '#22c55e' : '#ef4444',
          boxShadow: `0 0 5px ${connected ? '#22c55e88' : '#ef444488'}`,
        }} />
        <span style={{ fontSize: 11, color: connected ? '#4ade80' : '#f87171' }}>
          {connected ? '实时同步' : '离线模式'}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#475569' }}>
          {stats.length} 个技能有执行记录
        </span>
      </div>

      {/* 技能表现排行 */}
      <div style={{ ...S.card, flexShrink: 0, maxHeight: 260, overflowY: 'auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
          <div style={{ ...S.sectionTitle, marginBottom: 0 }}>技能表现排行</div>
          <button
            onClick={() => { fetchStats(); fetchSoftSkills() }}
            style={{ ...S.btn('#00d4ff'), marginLeft: 'auto', padding: '3px 10px', fontSize: 10 }}
          >
            ↻ 刷新
          </button>
        </div>

        {/* 图例 */}
        <div style={{ display: 'flex', gap: 12, marginBottom: 10, fontSize: 10 }}>
          {[['#22c55e', '≥80% 优秀'], ['#f59e0b', '50–79% 一般'], ['#ef4444', '<50% 差']].map(([c, l]) => (
            <span key={c} style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#64748b' }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: c, display: 'inline-block' }} />
              {l}
            </span>
          ))}
        </div>

        {sortedStats.length === 0 && (
          <div style={S.emptyMsg}>暂无技能执行数据</div>
        )}
        {sortedStats.map(s => (
          <BarRow
            key={s.name}
            name={s.name}
            successRate={s.successRate}
            avgCost={s.avgCost}
            total={s.total}
          />
        ))}
      </div>

      {/* 软技能区 */}
      <div style={{ ...S.card, flex: 1, overflowY: 'auto', minHeight: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
          <div style={{ ...S.sectionTitle, marginBottom: 0 }}>软技能库</div>
          <span style={{ marginLeft: 8, fontSize: 11, color: '#64748b' }}>
            {softSkills.length} 个
          </span>
        </div>

        {loading && (
          <div style={{ textAlign: 'center', color: '#475569', fontSize: 12, padding: '10px 0' }}>
            加载中…
          </div>
        )}
        {!loading && softSkills.length === 0 && (
          <div style={S.emptyMsg}>暂无软技能，可通过 AI 生成</div>
        )}
        {softSkills.map(skill => (
          <SoftSkillRow
            key={skill.name || skill.skill_id}
            skill={skill}
            onView={setViewSkill}
            onDelete={handleDeleteSoft}
          />
        ))}

        {/* 软技能详情弹窗 */}
        {viewSkill && (
          <div style={{
            position: 'fixed', inset: 0, zIndex: 1000,
            background: 'rgba(0,0,0,.6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }} onClick={() => setViewSkill(null)}>
            <div
              style={{
                background: 'rgba(15,23,42,.97)',
                border: '1px solid rgba(168,85,247,.4)',
                borderRadius: 10,
                padding: 18,
                minWidth: 320, maxWidth: 480, width: '90%',
                maxHeight: '70vh', overflowY: 'auto',
              }}
              onClick={e => e.stopPropagation()}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <span style={{ fontSize: 18 }}>🧩</span>
                <span style={{ fontWeight: 700, fontSize: 14, color: '#c084fc' }}>
                  {viewSkill.name || viewSkill.skill_id}
                </span>
                <button
                  onClick={() => setViewSkill(null)}
                  style={{ marginLeft: 'auto', ...S.btnSm }}
                >✕</button>
              </div>
              <pre style={S.pre}>{JSON.stringify(viewSkill, null, 2)}</pre>
            </div>
          </div>
        )}
      </div>

      {/* 操作按钮区 */}
      <div style={{ ...S.card, flexShrink: 0 }}>
        <div style={S.sectionTitle}>进化操作</div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button
            onClick={handlePatterns}
            disabled={!!opLoading}
            style={S.btn('#00d4ff')}
          >
            {opLoading === 'patterns' ? '检测中…' : '🔍 检测模式'}
          </button>
          <button
            onClick={handleGenerate}
            disabled={!!opLoading}
            style={S.btn('#a855f7')}
          >
            {opLoading === 'generate' ? '生成中…' : '✨ AI 生成'}
          </button>
          <button
            onClick={handleRetire}
            disabled={!!opLoading}
            style={S.btn('#f59e0b')}
          >
            {opLoading === 'retire' ? '检查中…' : '🗑 淘汰检查'}
          </button>
        </div>

        {/* 操作结果 */}
        {opResult && (
          <div style={{ marginTop: 10 }}>
            <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>
              {opResult.title}
            </div>
            <pre style={S.pre}>{JSON.stringify(opResult.data, null, 2)}</pre>
            <button
              onClick={() => setOpResult(null)}
              style={{ ...S.btnSm, marginTop: 6 }}
            >
              收起
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
