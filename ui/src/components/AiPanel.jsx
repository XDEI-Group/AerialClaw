/**
 * AiPanel.jsx — AI 模式面板（LLM 规划 + 执行报告）
 */
import { useState, useRef, useEffect } from 'react'

const EXAMPLE_TASKS = [
  '起飞到12米，向东飞30米，观察前方，然后返回起飞点降落',
  '起飞到15米，飞到坐标[-30, 40, -15]，寻找地面亮红色发光物体，向下观察后报告位置和周围物体',
  '飞到东南废墟区上空，在NED(-30,40)、(-50,60)、(-25,55)三个点各停留观察一次，记录地面物体颜色和形状，返航汇总报告',
]

export default function AiPanel({
  mode,
  isExecuting,
  lastAiPlan,
  lastAiReport,
  onSubmitTask,
  onStop,
  chatHistory = [],
  onSendChat,
}) {
  const [task, setTask] = useState('')
  const [useTools, setUseTools] = useState(false)
  const [chatMsg, setChatMsg] = useState('')
  const [activeTab, setActiveTab] = useState('chat') // 'chat' or 'task'
  const chatEndRef = useRef(null)

  const handleSubmit = () => {
    if (!task.trim() || isExecuting) return
    onSubmitTask(task.trim(), useTools)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) handleSubmit()
  }

  const handleChatSend = () => {
    if (!chatMsg.trim() || !onSendChat) return
    onSendChat(chatMsg.trim())
    setChatMsg('')
  }

  const handleChatKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleChatSend()
    }
  }

  // Auto-scroll chat
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [chatHistory])

  if (mode !== 'ai') {
    return (
      <div style={{
        height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        color: 'var(--text-dim)', gap: 12,
      }}>
        <span style={{ fontSize: 40 }}>🤖</span>
        <div style={{ fontSize: 13, textAlign: 'center' }}>
          切换到 <span style={{ color: '#a78bfa' }}>AI 模式</span> 以启用 LLM 自主规划
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>点击顶部 "AI" 按钮切换</div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%', overflow: 'hidden' }}>

      {/* AI 模式头部 */}
      <div style={{
        padding: '8px 12px',
        borderRadius: 'var(--radius)',
        background: 'rgba(124,58,237,.08)',
        border: '1px solid rgba(124,58,237,.3)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 16 }}>🧠</span>
          <span style={{ color: '#a78bfa', fontWeight: 600 }}>AI 自主规划模式</span>
          <div style={{
            marginLeft: 'auto',
            display: 'flex', alignItems: 'center', gap: 5,
          }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: 'var(--success)',
              boxShadow: '0 0 6px var(--success)',
            }} />
            <span style={{ color: 'var(--success)', fontSize: 11 }}>LLM 就绪</span>
          </div>
        </div>
      </div>

      {/* 任务输入 */}
      <div className="card" style={{ padding: 12, flexShrink: 0 }}>
        <div style={{ color: 'var(--text-dim)', fontSize: 10, marginBottom: 8 }}>
          输入自然语言任务指令 (Ctrl+Enter 执行)
        </div>
        <textarea
          value={task}
          onChange={e => setTask(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="例如：搜索北部区域，发现目标后拍照记录..."
          rows={3}
          style={{ resize: 'none', marginBottom: 8 }}
          disabled={isExecuting}
        />

        {/* 示例任务 */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
          {EXAMPLE_TASKS.map((t, i) => (
            <button
              key={i}
              className="btn"
              style={{ fontSize: 10, padding: '2px 8px' }}
              onClick={() => setTask(t)}
              disabled={isExecuting}
            >
              {t.slice(0, 18)}...
            </button>
          ))}
        </div>

        {/* 工具调用开关 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
          <label style={{
            display: 'flex', alignItems: 'center', gap: 6,
            cursor: 'pointer', fontSize: 11, color: 'var(--text-dim)',
          }}>
            <input
              type="checkbox"
              checked={useTools}
              onChange={e => setUseTools(e.target.checked)}
              style={{ width: 'auto', accentColor: 'var(--accent2)' }}
            />
            启用工具调用模式（LLM 可主动查询状态，精度更高但更慢）
          </label>
        </div>

        <div style={{ display: 'flex', gap: 6 }}>
          <button
            className="btn ai-mode"
            onClick={handleSubmit}
            disabled={isExecuting || !task.trim()}
            style={{ flex: 1 }}
          >
            {isExecuting ? (
              <>
                <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>⟳</span>
                规划执行中...
              </>
            ) : '🚀 开始 AI 规划执行'}
          </button>
          {isExecuting && (
            <button className="btn danger" onClick={onStop} style={{ padding: '6px 12px' }}>
              ⏹ 停止
            </button>
          )}
        </div>
      </div>

      {/* 规划结果 / 执行报告 / 对话 */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>

        {/* Tab 切换: 对话 / 任务 */}
        <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
          <button
            className="btn"
            onClick={() => setActiveTab('chat')}
            style={{
              flex: 1, fontSize: 11, padding: '4px 0',
              background: activeTab === 'chat' ? 'rgba(124,58,237,.15)' : 'transparent',
              color: activeTab === 'chat' ? '#a78bfa' : 'var(--text-dim)',
              border: activeTab === 'chat' ? '1px solid rgba(124,58,237,.4)' : '1px solid var(--border)',
            }}
          >
            💬 对话
          </button>
          <button
            className="btn"
            onClick={() => setActiveTab('task')}
            style={{
              flex: 1, fontSize: 11, padding: '4px 0',
              background: activeTab === 'task' ? 'rgba(124,58,237,.15)' : 'transparent',
              color: activeTab === 'task' ? '#a78bfa' : 'var(--text-dim)',
              border: activeTab === 'task' ? '1px solid rgba(124,58,237,.4)' : '1px solid var(--border)',
            }}
          >
            📋 执行报告
          </button>
        </div>

        {activeTab === 'chat' ? (
          /* 对话模式 */
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            {/* 聊天历史 */}
            <div style={{
              flex: 1, overflowY: 'auto', padding: '4px 0',
              display: 'flex', flexDirection: 'column', gap: 6,
            }}>
              {chatHistory.length === 0 && (
                <div style={{
                  color: 'var(--text-muted)', fontSize: 11,
                  textAlign: 'center', padding: 20,
                }}>
                  和你的无人机聊聊吧...
                </div>
              )}
              {chatHistory.map((msg, i) => (
                <div
                  key={i}
                  style={{
                    display: 'flex',
                    justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div style={{
                    maxWidth: '85%',
                    padding: '6px 10px',
                    borderRadius: 8,
                    fontSize: 11,
                    lineHeight: 1.5,
                    background: msg.role === 'user'
                      ? 'rgba(124,58,237,.15)'
                      : 'var(--bg)',
                    color: msg.role === 'user' ? '#c4b5fd' : 'var(--text)',
                    border: msg.role === 'user'
                      ? '1px solid rgba(124,58,237,.3)'
                      : '1px solid var(--border)',
                  }}>
                    {msg.content}
                    {msg.intent === 'THINKING' && (
                      <span style={{
                        display: 'inline-block', marginLeft: 6,
                        fontSize: 9, color: '#fbbf24',
                        background: 'rgba(251,191,36,.1)',
                        padding: '1px 4px', borderRadius: 3,
                      }}>思考中</span>
                    )}
                    {msg.intent === 'TASK' && (
                      <span style={{
                        display: 'inline-block', marginLeft: 6,
                        fontSize: 9, color: 'var(--accent)',
                        background: 'rgba(34,197,94,.1)',
                        padding: '1px 4px', borderRadius: 3,
                      }}>执行中</span>
                    )}
                    {msg.intent === 'RESULT' && (
                      <span style={{
                        display: 'inline-block', marginLeft: 6,
                        fontSize: 9, color: '#93c5fd',
                        background: 'rgba(59,130,246,.1)',
                        padding: '1px 4px', borderRadius: 3,
                      }}>执行结果</span>
                    )}
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* 聊天输入 */}
            <div style={{ display: 'flex', gap: 6, flexShrink: 0, paddingTop: 6 }}>
              <input
                type="text"
                value={chatMsg}
                onChange={e => setChatMsg(e.target.value)}
                onKeyDown={handleChatKeyDown}
                placeholder="输入消息..."
                style={{ flex: 1, fontSize: 11, padding: '6px 8px' }}
              />
              <button
                className="btn ai-mode"
                onClick={handleChatSend}
                disabled={!chatMsg.trim()}
                style={{ padding: '6px 12px', fontSize: 11 }}
              >
                发送
              </button>
            </div>
          </div>
        ) : (
          /* 任务执行报告 */
          <>
            {lastAiReport && <AiReportCard report={lastAiReport} />}
            {lastAiPlan && !lastAiReport?.ok && <AiPlanCard plan={lastAiPlan} />}
          </>
        )}
      </div>
    </div>
  )
}

// ── 规划卡片 ──────────────────────────────────────────────────────────────────

function AiPlanCard({ plan }) {
  if (!plan) return null
  const steps = plan.steps || []

  return (
    <div style={{
      padding: 12,
      borderRadius: 'var(--radius)',
      border: '1px solid rgba(124,58,237,.3)',
      background: 'rgba(124,58,237,.05)',
      animation: 'fadeIn .2s ease',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
        <span>📋</span>
        <span style={{ color: '#a78bfa', fontWeight: 600 }}>LLM 规划结果</span>
        <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 10 }}>
          {steps.length} 步
        </span>
      </div>

      {plan.reasoning && (
        <div style={{
          color: 'var(--text-dim)', fontSize: 11,
          padding: '6px 8px',
          background: 'var(--bg)',
          borderRadius: 4,
          marginBottom: 8,
          borderLeft: '2px solid rgba(124,58,237,.5)',
        }}>
          💭 {plan.reasoning}
        </div>
      )}

      {steps.map((step, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '5px 8px',
          borderRadius: 4,
          background: 'var(--bg)',
          marginBottom: 3,
          fontSize: 11,
        }}>
          <span style={{
            width: 18, height: 18,
            borderRadius: '50%',
            background: 'rgba(124,58,237,.3)',
            color: '#a78bfa',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 9, fontWeight: 700, flexShrink: 0,
          }}>{step.step}</span>
          <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{step.skill}</span>
          <span style={{ color: 'var(--text-dim)' }}>→</span>
          <span style={{ color: '#a78bfa' }}>{step.robot}</span>
          {step.parameters && Object.keys(step.parameters).length > 0 && (
            <span style={{ color: 'var(--text-dim)', fontSize: 10, marginLeft: 'auto' }}>
              {JSON.stringify(step.parameters).slice(0, 50)}
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

// ── 执行报告卡片 ──────────────────────────────────────────────────────────────

function AiReportCard({ report }) {
  if (!report) return null
  const ok = report.ok
  const stepResults = report.step_results || []

  return (
    <div style={{
      padding: 12,
      borderRadius: 'var(--radius)',
      border: `1px solid ${ok ? 'rgba(34,197,94,.3)' : 'rgba(239,68,68,.3)'}`,
      background: ok ? 'rgba(34,197,94,.04)' : 'rgba(239,68,68,.04)',
      animation: 'fadeIn .2s ease',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
        <span>{ok ? '✅' : '❌'}</span>
        <span style={{ fontWeight: 600, color: ok ? 'var(--success)' : 'var(--danger)' }}>
          {ok ? '任务执行成功' : '任务执行失败'}
        </span>
      </div>

      {/* 摘要 */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr',
        gap: 6, marginBottom: 8,
      }}>
        {[
          ['完成步骤', `${report.completed_steps}/${report.total_steps}`],
          ['耗时', `${report.cost_time?.toFixed(1)}s`],
          ...(report.replans > 0 ? [['重规划', `${report.replans}次`]] : []),
        ].map(([label, val]) => (
          <div key={label} style={{
            padding: '5px 8px',
            background: 'var(--bg)',
            borderRadius: 4,
            textAlign: 'center',
          }}>
            <div style={{ color: 'var(--text-dim)', fontSize: 9 }}>{label}</div>
            <div style={{ color: 'var(--text)', fontWeight: 600, fontSize: 12 }}>{val}</div>
          </div>
        ))}
      </div>

      {/* 步骤详情 */}
      {stepResults.map((r, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 8px',
          background: 'var(--bg)',
          borderRadius: 4,
          marginBottom: 3,
          fontSize: 11,
          borderLeft: `2px solid ${r.success ? 'var(--success)' : 'var(--danger)'}`,
        }}>
          <span>{r.success ? '✅' : '❌'}</span>
          <span style={{ color: 'var(--accent)' }}>{r.skill}</span>
          <span style={{ color: 'var(--text-dim)' }}>→</span>
          <span style={{ color: '#a78bfa' }}>{r.robot}</span>
          <span style={{ color: 'var(--text-dim)', marginLeft: 'auto', fontSize: 10 }}>
            {r.cost_time?.toFixed(2)}s
          </span>
          {!r.success && r.error && (
            <span style={{ color: 'var(--danger)', fontSize: 10 }}>{r.error}</span>
          )}
        </div>
      ))}
    </div>
  )
}
