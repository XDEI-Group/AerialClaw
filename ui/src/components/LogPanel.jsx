/**
 * LogPanel.jsx — 底部实时执行日志面板
 */
import { useEffect, useRef, useState } from 'react'

const LEVEL_STYLES = {
  info:    { color: '#e2e8f0', prefix: '  ' },
  success: { color: '#22c55e', prefix: '✅' },
  error:   { color: '#ef4444', prefix: '❌' },
  warn:    { color: '#f59e0b', prefix: '⚠️' },
  warning: { color: '#f59e0b', prefix: '⚠️' },
}

export default function LogPanel({ logs }) {
  const bottomRef = useRef(null)
  const containerRef = useRef(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  // 检测用户是否手动滚动
  const handleScroll = () => {
    const el = containerRef.current
    if (!el) return
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoScroll(isAtBottom)
  }

  // 过滤日志
  const filtered = logs.filter(entry => {
    if (filter !== 'all' && entry.level !== filter) return false
    if (search && !entry.msg?.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const formatTime = (ts) => {
    const d = new Date(ts)
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}.${String(d.getMilliseconds()).padStart(3,'0')}`
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100%',
      background: 'var(--bg-panel)',
    }}>
      {/* 工具栏 */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '4px 10px',
        borderTop: '1px solid var(--border)',
        borderBottom: '1px solid var(--border)',
        flexShrink: 0,
        background: 'var(--bg-card)',
      }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 10, marginRight: 4 }}>日志</span>

        {/* 级别过滤 */}
        {['all', 'success', 'error', 'warn', 'info'].map(l => (
          <button
            key={l}
            className={`btn ${filter === l ? 'primary' : ''}`}
            onClick={() => setFilter(l)}
            style={{ fontSize: 9, padding: '2px 7px' }}
          >
            {l === 'all' ? '全部' : l}
          </button>
        ))}

        {/* 搜索 */}
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="搜索日志..."
          style={{ width: 120, fontSize: 10, padding: '2px 7px' }}
        />

        <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontSize: 9 }}>
          {filtered.length} 条
        </span>

        {/* 自动滚动 */}
        <button
          className={`btn ${autoScroll ? 'success' : ''}`}
          onClick={() => {
            setAutoScroll(true)
            bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
          }}
          style={{ fontSize: 9, padding: '2px 7px' }}
        >
          ↓ 跟随
        </button>

        {/* 清空 */}
        <button
          className="btn"
          onClick={() => {}}
          style={{ fontSize: 9, padding: '2px 7px', color: 'var(--text-dim)' }}
        >
          清空
        </button>
      </div>

      {/* 日志内容 */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        style={{
          flex: 1, overflowY: 'auto',
          padding: '4px 10px',
          fontFamily: 'var(--font)',
          fontSize: 11,
          lineHeight: 1.6,
        }}
      >
        {filtered.length === 0 && (
          <div style={{ color: 'var(--text-muted)', padding: '8px 0' }}>
            等待系统日志...
          </div>
        )}

        {filtered.map((entry, i) => {
          const style = LEVEL_STYLES[entry.level] || LEVEL_STYLES.info
          return (
            <div
              key={i}
              style={{
                display: 'flex', gap: 8,
                padding: '1px 0',
                borderBottom: i < filtered.length - 1 ? '1px solid rgba(30,45,74,.5)' : 'none',
                animation: i === filtered.length - 1 ? 'fadeIn .15s ease' : 'none',
              }}
            >
              <span style={{ color: 'var(--text-muted)', flexShrink: 0, fontSize: 10 }}>
                {formatTime(entry.ts)}
              </span>
              <span style={{ flexShrink: 0, width: 16 }}>{style.prefix}</span>
              <span style={{ color: style.color }}>
                {entry.msg}
              </span>
              {entry.skill && (
                <span style={{ color: 'var(--accent)', fontSize: 10, marginLeft: 4 }}>
                  [{entry.skill}]
                </span>
              )}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
