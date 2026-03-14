/**
 * Header.jsx — 顶部状态栏
 */
export default function Header({ connected, systemStatus, onInit, onModeSwitch, onStop }) {
  const { initialized, mode, is_executing } = systemStatus

  return (
    <header style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '0 16px', height: 44,
      background: 'var(--bg-panel)',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginRight: 8 }}>
        <span style={{ fontSize: 18 }}>🤖</span>
        <span style={{ color: 'var(--accent)', fontWeight: 700, fontSize: 14, letterSpacing: 1 }}>
          AERIALCLAW
        </span>
        <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>控制台</span>
      </div>

      {/* 连接状态 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <div style={{
          width: 7, height: 7, borderRadius: '50%',
          background: connected ? 'var(--success)' : 'var(--danger)',
          boxShadow: connected ? '0 0 6px var(--success)' : 'none',
          animation: connected ? 'none' : 'pulse 1s infinite',
        }} />
        <span style={{ color: connected ? 'var(--success)' : 'var(--danger)', fontSize: 11 }}>
          {connected ? 'ONLINE' : 'OFFLINE'}
        </span>
      </div>

      <div style={{ width: 1, height: 20, background: 'var(--border)', margin: '0 4px' }} />

      {/* 初始化按钮 */}
      {!initialized && (
        <button className="btn primary" onClick={onInit} style={{ fontSize: 11 }}>
          ⚡ 初始化系统
        </button>
      )}

      {initialized && (
        <span style={{ color: 'var(--success)', fontSize: 11 }}>✅ 系统就绪</span>
      )}

      <div style={{ flex: 1 }} />

      {/* 执行状态 + 打断按钮（始终可见） */}
      {initialized && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {is_executing && (
            <>
              <div style={{
                width: 6, height: 6, borderRadius: '50%',
                background: 'var(--warning)',
                animation: 'pulse .6s infinite',
              }} />
              <span style={{ color: 'var(--warning)', fontSize: 11 }}>执行中</span>
            </>
          )}
          <button
            className="btn danger"
            onClick={onStop}
            style={{
              padding: '3px 10px', fontSize: 11,
              opacity: is_executing ? 1 : 0.5,
            }}
          >
            ⏹ 打断
          </button>
        </div>
      )}

      {/* 模式切换 */}
      <div style={{ display: 'flex', gap: 4 }}>
        <button
          className={`btn ${mode === 'manual' ? 'primary' : ''}`}
          onClick={() => onModeSwitch('manual')}
          disabled={!initialized}
          style={{ fontSize: 11, padding: '4px 12px' }}
        >
          🕹 手动
        </button>
        <button
          className={`btn ${mode === 'ai' ? 'ai-mode' : ''}`}
          onClick={() => onModeSwitch('ai')}
          disabled={!initialized}
          style={{ fontSize: 11, padding: '4px 12px' }}
        >
          🤖 AI
        </button>
      </div>

      {/* 当前模式指示 */}
      <span className={`badge ${mode}`} style={{ marginLeft: 4 }}>
        {mode === 'manual' ? '手动模式' : 'AI 模式'}
      </span>
    </header>
  )
}
