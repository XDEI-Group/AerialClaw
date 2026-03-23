import { useState, useRef, useEffect, useCallback } from 'react';
import { io } from 'socket.io-client';

const C = {
  bg: '#0f172a',
  surface: 'rgba(255,255,255,.04)',
  border: 'rgba(255,255,255,.08)',
  accent: '#00d4ff',
  success: '#4ade80',
  error: '#f87171',
  warn: '#fbbf24',
  text: '#e2e8f0',
  dim: '#64748b',
  tool: '#0d2318',
  toolBorder: '#4ade8030',
  result: '#0d1e2e',
  resultBorder: '#00d4ff25',
  user: '#1a2a4a',
  assistant: 'rgba(255,255,255,.04)',
};

function ToolCard({ tool, args, result }) {
  const [open, setOpen] = useState(false);
  const argsStr = args ? JSON.stringify(args) : '{}';
  const resultStr = result ? JSON.stringify(result, null, 2) : '';
  const success = !result || result.success !== false;
  const pending = !result;
  return (
    <div style={{ margin: '4px 0', borderRadius: 8, border: `1px solid ${pending ? C.border : success ? C.toolBorder : '#f8717130'}`, background: pending ? C.surface : success ? C.tool : '#2a0d0d', fontSize: 13 }}>
      <div onClick={() => result && setOpen(o => !o)} style={{ padding: '7px 12px', cursor: result ? 'pointer' : 'default', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: pending ? C.warn : success ? C.success : C.error, fontFamily: 'monospace' }}>
          {pending ? '⏳' : success ? '✓' : '✗'} {tool}
        </span>
        <span style={{ color: C.dim, fontFamily: 'monospace', fontSize: 11, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          ({argsStr.length > 80 ? argsStr.slice(0, 80) + '…' : argsStr})
        </span>
        {result && <span style={{ color: C.dim, fontSize: 10 }}>{open ? '▲' : '▼'}</span>}
      </div>
      {open && result && (
        <pre style={{ margin: 0, padding: '8px 12px', borderTop: `1px solid ${C.border}`, color: C.dim, fontSize: 11, overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 200, overflowY: 'auto' }}>
          {resultStr.length > 2000 ? resultStr.slice(0, 2000) + '\n…(truncated)' : resultStr}
        </pre>
      )}
    </div>
  );
}

function Bubble({ msg }) {
  const isUser = msg.role === 'user';
  if (msg.role === 'tool') return <ToolCard tool={msg.tool} args={msg.args} result={msg.result} />;
  if (msg.role === 'thinking') return (
    <div style={{ margin: '3px 0', padding: '6px 12px', borderRadius: 8, background: 'rgba(251,191,36,.06)', border: '1px solid rgba(251,191,36,.2)', fontSize: 12, color: '#a08040', fontStyle: 'italic', lineHeight: 1.5 }}>
      💭 {msg.content}
    </div>
  );
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', margin: '4px 0' }}>
      <div style={{
        maxWidth: '85%', padding: '10px 14px',
        borderRadius: isUser ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
        background: isUser ? C.user : C.assistant,
        border: '1px solid ' + C.border,
        fontSize: 14, lineHeight: 1.6, color: C.text,
        whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      }}>
        {msg.content}
      </div>
    </div>
  );
}

export default function DoctorPanel() {
  const [tab, setTab] = useState('chat');
  const [chatHistory, setChatHistory] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [thinkingText, setThinkingText] = useState('');
  const [autoSteps, setAutoSteps] = useState([]);
  const [autoRunning, setAutoRunning] = useState(false);
  const [diagResult, setDiagResult] = useState(null);
  const [diagLoading, setDiagLoading] = useState(false);

  const socketRef = useRef(null);
  const bottomRef = useRef(null);
  const autoBottomRef = useRef(null);
  const timeoutRef = useRef(null);
  const replyHandlerRef = useRef(null);
  const inputRef = useRef(null);
  const retryCountRef = useRef(0);
  const lastMsgRef = useRef(null);
  const lastHistoryRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chatHistory, thinkingText]);
  useEffect(() => { autoBottomRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [autoSteps]);

  useEffect(() => {
    // 启动时从后端拉取持久化历史
    fetch('/api/doctor/chat_history')
      .then(r => r.json())
      .then(data => {
        if (data.history && data.history.length > 0) {
          setChatHistory(data.history);
        }
      })
      .catch(() => {});

    const socket = io({ path: '/socket.io', transports: ['websocket'] });
    socketRef.current = socket;
    socket.on('doctor_step', (step) => {
      setAutoSteps(prev => [...prev, step]);
      if (step.done) setAutoRunning(false);
    });
    socket.on('doctor_chat_step', (step) => {
      // Step C（done=true 且无 tool）：由 doctor_reply 处理，此处忽略
      if (step.done && !step.tool) return;

      // Step A（工具调用前）：先追加 thinking 气泡，再追加 pending 工具卡片
      if (step.tool && !step.result) {
        setChatHistory(prev => {
          const next = [...prev];
          // 追加 thinking 气泡（如果有且非空）
          if (step.thinking) {
            next.push({ role: 'thinking', content: step.thinking });
          }
          // 追加 pending 工具卡片
          next.push({ role: 'tool', tool: step.tool, args: step.args, result: null });
          return next;
        });
        setThinkingText('执行 ' + step.tool + '...');
        return;
      }

      // Step B（工具结果）：找到最后一个匹配的 pending 工具卡片，更新 result
      if (step.tool && step.result) {
        setChatHistory(prev => {
          const copy = [...prev];
          for (let i = copy.length - 1; i >= 0; i--) {
            if (copy[i].role === 'tool' && copy[i].tool === step.tool && !copy[i].result) {
              copy[i] = { ...copy[i], result: step.result };
              break;
            }
          }
          return copy;
        });
        setThinkingText('');
        return;
      }

      // 仅有 thinking 但无 tool 的 step（边界情况）
      if (step.thinking) {
        setThinkingText(step.thinking.slice(0, 120));
        setChatHistory(prev => [...prev, { role: 'thinking', content: step.thinking }]);
      }
    });
    return () => socket.disconnect();
  }, []);

  const abort = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    const socket = socketRef.current;
    if (socket && replyHandlerRef.current) {
      socket.off('doctor_reply', replyHandlerRef.current);
      // 通知后端停止
      socket.emit('doctor_chat_stop', {});
    }
    setLoading(false);
    setThinkingText('');
    retryCountRef.current = 0;
    setChatHistory(prev => [...prev.filter(m => m.role !== 'thinking'), { role: 'assistant', content: '⏹ 已打断' }]);
  }, []);

  const doSend = useCallback((msg, history) => {
    const socket = socketRef.current;
    if (!socket) { setLoading(false); setThinkingText(''); return; }

    const handler = (data) => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      setLoading(false);
      setThinkingText('');
      retryCountRef.current = 0;
      setChatHistory(prev => {
        const next = [...prev, { role: 'assistant', content: data.reply || data.error || '（无回复）' }];
        // 持久化到后端（只保存 user/assistant，不保存 thinking/tool 卡片）
        const slim = next.filter(m => m.role === 'user' || m.role === 'assistant');
        fetch('/api/doctor/chat_history', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ history: slim }),
        }).catch(() => {});
        return next;
      });
    };
    replyHandlerRef.current = handler;
    socket.once('doctor_reply', handler);

    timeoutRef.current = setTimeout(() => {
      socket.off('doctor_reply', handler);
      if (retryCountRef.current < 1) {
        retryCountRef.current += 1;
        setThinkingText('网络慢，自动重试…');
        doSend(msg, history);
      } else {
        retryCountRef.current = 0;
        setLoading(false);
        setThinkingText('');
        setChatHistory(prev => [...prev, { role: 'assistant', content: '⚠️ 两次超时，请检查 server 状态后重试' }]);
      }
    }, 90000);

    socket.emit('doctor_chat', { message: msg, history });
  }, []);

  const send = useCallback(() => {
    const msg = input.trim();
    if (!msg || loading) return;
    setInput('');
    setLoading(true);
    setThinkingText('思考中…');
    retryCountRef.current = 0;
    const history = chatHistory
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({ role: m.role, content: m.content }));
    setChatHistory(prev => [...prev, { role: 'user', content: msg }]);
    lastMsgRef.current = msg;
    lastHistoryRef.current = history;
    doSend(msg, history);
  }, [input, loading, chatHistory, doSend]);

  const startAuto = () => { setAutoSteps([]); setAutoRunning(true); socketRef.current?.emit('doctor_run', {}); };
  const stopAuto = () => { fetch('/api/doctor/stop', { method: 'POST' }); setAutoRunning(false); };
  const clearHistory = () => {
    fetch('/api/doctor/chat_history/clear', { method: 'POST' }).catch(() => {});
    setChatHistory([]);
  };

  const runDiag = async () => {
    setDiagLoading(true); setDiagResult(null);
    try { setDiagResult(await (await fetch('/api/doctor/diagnose')).json()); }
    catch (e) { setDiagResult({ score: 0, issues: [{ name: 'Error', message: e.message }], passed: [] }); }
    setDiagLoading(false);
  };

  const TABS = [
    { key: 'chat', label: '💬 对话' },
    { key: 'auto', label: '🤖 自主' },
    { key: 'diag', label: '🩺 诊断' },
  ];

  const tabStyle = (active) => ({
    padding: '8px 20px', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
    background: active ? C.accent : 'transparent', color: active ? '#000' : C.dim,
    borderRadius: '8px 8px 0 0', transition: 'all .15s',
  });

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: C.bg, color: C.text, fontFamily: "'Inter',system-ui,sans-serif", overflow: 'hidden' }}>

      {/* Tab 栏 */}
      <div style={{ display: 'flex', alignItems: 'flex-end', padding: '10px 16px 0', borderBottom: `1px solid ${C.border}`, flexShrink: 0, gap: 2 }}>
        {TABS.map(t => <button key={t.key} onClick={() => setTab(t.key)} style={tabStyle(tab === t.key)}>{t.label}</button>)}
        <div style={{ flex: 1 }} />
        {tab === 'chat' && chatHistory.length > 0 && (
          <button onClick={clearHistory} style={{ fontSize: 11, color: C.dim, background: 'none', border: 'none', cursor: 'pointer', paddingBottom: 10, paddingRight: 4 }} title="清空对话">🗑 清空</button>
        )}
        <span style={{ fontSize: 11, color: C.dim, paddingBottom: 10, paddingRight: 4 }}>Doctor Agent</span>
      </div>

      {/* ── 对话 Tab ─────────────────────────────────────────── */}
      {tab === 'chat' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
            {chatHistory.length === 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 10, color: C.dim }}>
                <div style={{ fontSize: 36 }}>🩺</div>
                <div style={{ fontSize: 15, color: C.text }}>告诉我你遇到了什么问题</div>
                <div style={{ fontSize: 12 }}>Doctor 会诊断 Adapter、读取源码、自动修复</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8, justifyContent: 'center' }}>
                  {['起飞后 fly_to 报 RPC 错误', '降落后无法再次起飞', '诊断整个 adapter'].map(q => (
                    <button key={q} onClick={() => { setInput(q); inputRef.current?.focus(); }}
                      style={{ padding: '7px 14px', borderRadius: 20, border: `1px solid ${C.border}`, background: C.surface, color: C.text, cursor: 'pointer', fontSize: 12 }}>
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {chatHistory.map((m, i) => <Bubble key={i} msg={m} />)}
            {loading && thinkingText && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 2px', color: C.dim, fontSize: 13 }}>
                <span style={{ display: 'inline-block', animation: 'pulse 1.2s ease-in-out infinite' }}>●</span>
                {thinkingText}
              </div>
            )}
            <div ref={bottomRef} />
          </div>
          <div style={{ padding: '10px 14px', borderTop: `1px solid ${C.border}`, display: 'flex', gap: 8, flexShrink: 0 }}>
            <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), send())}
              placeholder="描述问题…" disabled={loading}
              style={{ flex: 1, padding: '10px 14px', borderRadius: 10, border: `1px solid ${C.border}`, background: C.surface, color: C.text, fontSize: 14, outline: 'none' }}
            />
            {loading
              ? <button onClick={abort} style={{ padding: '10px 18px', borderRadius: 10, border: 'none', background: C.error, color: '#fff', cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>⏹ 打断</button>
              : <button onClick={send} disabled={!input.trim()} style={{ padding: '10px 18px', borderRadius: 10, border: 'none', background: input.trim() ? C.accent : C.surface, color: input.trim() ? '#000' : C.dim, cursor: input.trim() ? 'pointer' : 'default', fontWeight: 600, fontSize: 13 }}>发送</button>
            }
          </div>
        </div>
      )}

      {/* ── 自主 Tab ───────────────────────────────────────────── */}
      {tab === 'auto' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ padding: '12px 16px', display: 'flex', gap: 8, flexShrink: 0, borderBottom: `1px solid ${C.border}` }}>
            <button onClick={startAuto} disabled={autoRunning}
              style={{ padding: '8px 18px', borderRadius: 8, border: 'none', background: autoRunning ? C.surface : C.accent, color: autoRunning ? C.dim : '#000', cursor: autoRunning ? 'default' : 'pointer', fontWeight: 600, fontSize: 13 }}>
              {autoRunning ? '⏳ 运行中…' : '🚀 开始自主诊断'}
            </button>
            {autoRunning && <button onClick={stopAuto} style={{ padding: '8px 18px', borderRadius: 8, border: 'none', background: C.error, color: '#fff', cursor: 'pointer', fontWeight: 600, fontSize: 13 }}>⏹ 停止</button>}
            {autoSteps.length > 0 && !autoRunning && <button onClick={() => setAutoSteps([])} style={{ padding: '8px 18px', borderRadius: 8, border: `1px solid ${C.border}`, background: 'transparent', color: C.dim, cursor: 'pointer', fontSize: 13 }}>清空</button>}
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
            {autoSteps.length === 0 && !autoRunning && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: C.dim, gap: 8 }}>
                <div style={{ fontSize: 32 }}>🤖</div>
                <div>点击开始，Doctor 将自主诊断并修复所有 adapter 问题</div>
              </div>
            )}
            {autoSteps.map((step, i) => (
              <div key={i} style={{ marginBottom: 8, padding: '10px 14px', borderRadius: 10, border: `1px solid ${C.border}`, background: C.surface, fontSize: 13 }}>
                <div style={{ color: C.dim, fontSize: 11, marginBottom: 4 }}>Step {step.iteration || i + 1}</div>
                {step.thinking && <div style={{ color: C.text, marginBottom: 6, lineHeight: 1.5 }}>💭 {step.thinking}</div>}
                {step.tool && <ToolCard tool={step.tool} args={step.args} result={step.result} />}
                {step.done && !step.tool && step.result?.message && (
                  <div style={{ color: C.success }}>✅ {step.result.message}</div>
                )}
              </div>
            ))}
            <div ref={autoBottomRef} />
          </div>
        </div>
      )}

      {/* ── 诊断 Tab ──────────────────────────────────────────── */}
      {tab === 'diag' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ padding: '12px 16px', flexShrink: 0, borderBottom: `1px solid ${C.border}` }}>
            <button onClick={runDiag} disabled={diagLoading}
              style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: diagLoading ? C.surface : C.accent, color: diagLoading ? C.dim : '#000', cursor: diagLoading ? 'default' : 'pointer', fontWeight: 600, fontSize: 13 }}>
              {diagLoading ? '⏳ 检测中…' : '🔍 运行快速诊断'}
            </button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
            {!diagResult && !diagLoading && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: C.dim, gap: 8 }}>
                <div style={{ fontSize: 32 }}>🔍</div>
                <div>点击运行，检查 adapter 合规状态</div>
              </div>
            )}
            {diagResult && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                  <div style={{ fontSize: 36, fontWeight: 700, color: diagResult.score >= 80 ? C.success : diagResult.score >= 50 ? C.warn : C.error }}>{diagResult.score ?? 0}</div>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 15 }}>健康评分</div>
                    <div style={{ color: C.dim, fontSize: 12 }}>{diagResult.summary || ''}</div>
                  </div>
                </div>
                {diagResult.issues?.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 12, color: C.dim, marginBottom: 6, fontWeight: 600 }}>❌ 问题</div>
                    {diagResult.issues.map((iss, i) => (
                      <div key={i} style={{ padding: '8px 12px', borderRadius: 8, background: '#2a0d0d', border: `1px solid #f8717130`, marginBottom: 6, fontSize: 13 }}>
                        <span style={{ color: C.error, fontWeight: 600 }}>{iss.name}</span>
                        <span style={{ color: C.text, marginLeft: 8 }}>{iss.message}</span>
                        {iss.fix_hint && <div style={{ color: C.dim, fontSize: 11, marginTop: 4 }}>💡 {iss.fix_hint}</div>}
                      </div>
                    ))}
                  </div>
                )}
                {diagResult.passed?.length > 0 && (
                  <div>
                    <div style={{ fontSize: 12, color: C.dim, marginBottom: 6, fontWeight: 600 }}>✅ 通过</div>
                    {diagResult.passed.map((p, i) => (
                      <div key={i} style={{ padding: '6px 12px', borderRadius: 8, background: C.tool, border: `1px solid ${C.toolBorder}`, marginBottom: 4, fontSize: 13, color: C.success }}>{typeof p === 'string' ? p : p.name}</div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <style>{`
        @keyframes pulse { 0%,100%{opacity:.3} 50%{opacity:1} }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,.15); border-radius: 4px; }
      `}</style>
    </div>
  );
}
