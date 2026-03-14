/**
 * ModelConfig.jsx — LLM 模型配置面板
 * 显示当前模型、切换 provider、配置新渠道
 */
import { useState, useEffect, useCallback } from 'react'

const API = window.location.protocol + '//' + window.location.hostname + ':5001'

export default function ModelConfig({ collapsed = false }) {
  const [config, setConfig] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [showModules, setShowModules] = useState(false)
  const [error, setError] = useState('')

  // 新渠道表单
  const [newProvider, setNewProvider] = useState({
    name: '', base_url: '', api_key: '', default_model: '', timeout: 60,
  })

  const fetchConfig = useCallback(() => {
    setLoading(true)
    fetch(`${API}/api/llm/config`)
      .then(r => r.json())
      .then(data => { if (data.ok) setConfig(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => { fetchConfig() }, [fetchConfig])

  const switchProvider = (provider) => {
    fetch(`${API}/api/llm/active`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider }),
    })
      .then(r => r.json())
      .then(data => { if (data.ok) fetchConfig() })
      .catch(e => setError(e.message))
  }

  const updateModule = (mod, provider, model) => {
    fetch(`${API}/api/llm/module/${mod}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: provider || null, model: model || null }),
    })
      .then(r => r.json())
      .then(data => { if (data.ok) fetchConfig() })
      .catch(e => setError(e.message))
  }

  const addProvider = () => {
    if (!newProvider.name || !newProvider.base_url || !newProvider.default_model) {
      setError('名称、URL 和模型不能为空')
      return
    }
    fetch(`${API}/api/llm/provider`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newProvider),
    })
      .then(r => r.json())
      .then(data => {
        if (data.ok) {
          fetchConfig()
          setShowAdd(false)
          setNewProvider({ name: '', base_url: '', api_key: '', default_model: '', timeout: 60 })
          setError('')
        } else {
          setError(data.msg || '添加失败')
        }
      })
      .catch(e => setError(e.message))
  }

  const deleteProvider = (name) => {
    if (!confirm(`确定删除渠道 "${name}"?`)) return
    fetch(`${API}/api/llm/provider/${name}`, { method: 'DELETE' })
      .then(r => r.json())
      .then(data => {
        if (data.ok) fetchConfig()
        else setError(data.msg || '删除失败')
      })
      .catch(e => setError(e.message))
  }

  if (loading && !config) {
    return <div style={{ color: 'var(--text-muted)', fontSize: 11, padding: 8 }}>加载配置中...</div>
  }
  if (!config) {
    return <div style={{ color: 'var(--text-muted)', fontSize: 11, padding: 8 }}>无法加载 LLM 配置</div>
  }

  const { active_provider, providers, modules } = config

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>

      {/* 当前模型指示器 */}
      <div style={{
        padding: '8px 10px',
        borderRadius: 'var(--radius)',
        background: 'rgba(59,130,246,.06)',
        border: '1px solid rgba(59,130,246,.25)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontSize: 14 }}>🧠</span>
          <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>当前模型</span>
        </div>
        <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600, color: '#93c5fd' }}>
          {providers[active_provider]?.default_model || '?'}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
          {active_provider} · {providers[active_provider]?.base_url || ''}
        </div>
      </div>

      {/* 渠道列表 + 切换 */}
      <div style={{ fontSize: 10, color: 'var(--text-dim)', fontWeight: 600, marginTop: 4 }}>
        可用渠道
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {Object.entries(providers).map(([name, p]) => (
          <div
            key={name}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '5px 8px',
              borderRadius: 4,
              background: name === active_provider ? 'rgba(59,130,246,.12)' : 'var(--bg)',
              border: name === active_provider ? '1px solid rgba(59,130,246,.3)' : '1px solid var(--border)',
              cursor: 'pointer',
              transition: 'all .15s',
            }}
            onClick={() => switchProvider(name)}
          >
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: name === active_provider ? '#3b82f6' : 'var(--text-muted)',
              boxShadow: name === active_provider ? '0 0 6px #3b82f6' : 'none',
              flexShrink: 0,
            }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 11,
                fontWeight: name === active_provider ? 600 : 400,
                color: name === active_provider ? '#93c5fd' : 'var(--text)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {name}
              </div>
              <div style={{
                fontSize: 9, color: 'var(--text-muted)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {p.default_model} · {p.base_url?.replace(/https?:\/\//, '')}
              </div>
            </div>
            {name !== active_provider && (
              <button
                onClick={(e) => { e.stopPropagation(); deleteProvider(name) }}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', fontSize: 12, padding: '0 2px',
                  opacity: 0.5,
                }}
                title="删除渠道"
              >×</button>
            )}
          </div>
        ))}
      </div>

      {/* 模块配置 (可折叠) */}
      <button
        className="btn"
        onClick={() => setShowModules(!showModules)}
        style={{ fontSize: 10, padding: '3px 8px', color: 'var(--text-dim)' }}
      >
        {showModules ? '▾' : '▸'} 模块配置
      </button>
      {showModules && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {Object.entries(modules).map(([mod, mc]) => (
            <div key={mod} style={{
              padding: '5px 8px',
              background: 'var(--bg)',
              borderRadius: 4,
              border: '1px solid var(--border)',
            }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-dim)', marginBottom: 3 }}>
                {mod}
              </div>
              <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                <select
                  value={mc.provider || ''}
                  onChange={e => updateModule(mod, e.target.value, mc.model)}
                  style={{ flex: 1, fontSize: 10, padding: '2px 4px' }}
                >
                  <option value="">跟随全局 ({active_provider})</option>
                  {Object.keys(providers).map(n => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
                <input
                  type="text"
                  value={mc.model || ''}
                  onChange={e => updateModule(mod, mc.provider, e.target.value)}
                  placeholder={mc.resolved_model || '默认模型'}
                  style={{ width: 80, fontSize: 10, padding: '2px 4px' }}
                />
              </div>
              <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>
                实际: {mc.resolved_provider}/{mc.resolved_model}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 添加新渠道 */}
      <button
        className="btn"
        onClick={() => { setShowAdd(!showAdd); setError('') }}
        style={{
          fontSize: 10, padding: '4px 8px',
          color: showAdd ? 'var(--danger)' : 'var(--accent)',
          border: `1px solid ${showAdd ? 'rgba(239,68,68,.3)' : 'rgba(34,197,94,.3)'}`,
        }}
      >
        {showAdd ? '✕ 取消' : '＋ 添加渠道'}
      </button>

      {showAdd && (
        <div style={{
          padding: 10,
          background: 'var(--bg)',
          borderRadius: 'var(--radius)',
          border: '1px solid var(--border)',
          display: 'flex', flexDirection: 'column', gap: 6,
        }}>
          <input
            type="text"
            placeholder="渠道名称 (如 my_openai)"
            value={newProvider.name}
            onChange={e => setNewProvider(p => ({...p, name: e.target.value}))}
            style={{ fontSize: 11, padding: '4px 8px' }}
          />
          <input
            type="text"
            placeholder="Base URL (如 https://api.openai.com/v1)"
            value={newProvider.base_url}
            onChange={e => setNewProvider(p => ({...p, base_url: e.target.value}))}
            style={{ fontSize: 11, padding: '4px 8px' }}
          />
          <input
            type="password"
            placeholder="API Key (本地服务可留空)"
            value={newProvider.api_key}
            onChange={e => setNewProvider(p => ({...p, api_key: e.target.value}))}
            style={{ fontSize: 11, padding: '4px 8px' }}
          />
          <input
            type="text"
            placeholder="默认模型 (如 gpt-4o)"
            value={newProvider.default_model}
            onChange={e => setNewProvider(p => ({...p, default_model: e.target.value}))}
            style={{ fontSize: 11, padding: '4px 8px' }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>超时(秒)</span>
            <input
              type="number"
              value={newProvider.timeout}
              onChange={e => setNewProvider(p => ({...p, timeout: parseInt(e.target.value) || 60}))}
              style={{ width: 60, fontSize: 11, padding: '4px 6px' }}
            />
          </div>
          <button className="btn ai-mode" onClick={addProvider} style={{ fontSize: 11, padding: '5px 0' }}>
            确认添加
          </button>
        </div>
      )}

      {error && (
        <div style={{ color: 'var(--danger)', fontSize: 10, padding: '4px 8px' }}>{error}</div>
      )}
    </div>
  )
}
