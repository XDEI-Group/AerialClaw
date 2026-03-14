import { useState, useEffect, useRef, useCallback } from 'react';

const SPEED = 3;
const YAW_SPEED = 45;
const DOWN_UP = -2;
const DOWN_DN = 2;
const SEND_INTERVAL = 200;
const TELEMETRY_POLL = 500;
const CYAN = '#00d4ff';
const GLASS_BG = 'rgba(0,0,0,0.7)';
const GLASS_BORDER = 'rgba(0,212,255,0.25)';
const BADGE_BG = 'rgba(0,0,0,0.65)';
const BTN_ACTIVE_BG = 'rgba(0,212,255,0.25)';
const BTN_INACTIVE_BG = 'rgba(10,14,26,0.85)';
const BTN_DIM_BORDER = 'rgba(0,212,255,0.15)';

function CornerBracket({ top, left, right, bottom }) {
  const size = 32, thick = 3;
  const base = { position: 'absolute', width: size, height: size, pointerEvents: 'none', zIndex: 2 };
  if (top !== undefined) base.top = top;
  if (bottom !== undefined) base.bottom = bottom;
  if (left !== undefined) base.left = left;
  if (right !== undefined) base.right = right;
  const isTop = top !== undefined, isLeft = left !== undefined;
  const hBar = { position: 'absolute', width: size, height: thick, background: CYAN };
  hBar[isTop ? 'top' : 'bottom'] = 0;
  hBar[isLeft ? 'left' : 'right'] = 0;
  const vBar = { position: 'absolute', width: thick, height: size, background: CYAN };
  vBar[isTop ? 'top' : 'bottom'] = 0;
  vBar[isLeft ? 'left' : 'right'] = 0;
  return (<div style={base}><div style={hBar} /><div style={vBar} /></div>);
}

function PiPCamera({ image, label }) {
  return (
    <div style={{ width: 130, height: 75, borderRadius: 6, overflow: 'hidden', border: '1px solid ' + GLASS_BORDER, position: 'relative', background: '#111', flexShrink: 0 }}>
      {image && <img src={'data:image/jpeg;base64,' + image} alt={label} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />}
      <span style={{ position: 'absolute', bottom: 2, left: 4, fontSize: 10, fontFamily: 'monospace', color: '#0f0', background: 'rgba(0,0,0,0.7)', padding: '1px 4px', borderRadius: 3 }}>{label}</span>
    </div>
  );
}

function CtrlBtn({ label, active, onDown, onUp, wide }) {
  const w = wide ? 64 : 48;
  return (
    <button
      onMouseDown={onDown} onMouseUp={onUp} onMouseLeave={onUp}
      onTouchStart={onDown} onTouchEnd={onUp} onTouchCancel={onUp}
      style={{
        width: w, height: 48, borderRadius: 6,
        border: '1px solid ' + (active ? CYAN : BTN_DIM_BORDER),
        background: active ? BTN_ACTIVE_BG : BTN_INACTIVE_BG,
        color: active ? CYAN : 'rgba(0,212,255,0.5)',
        fontFamily: 'monospace', fontWeight: 'bold', fontSize: 16,
        cursor: 'pointer', outline: 'none', pointerEvents: 'auto',
        boxShadow: active ? '0 0 12px rgba(0,212,255,0.27)' : 'none',
        transition: 'all 0.1s',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        userSelect: 'none', WebkitUserSelect: 'none', padding: 0, margin: 0,
      }}
    >{label}</button>
  );
}

export default function CockpitView({ socket, sensorCameras, sensorLidar, onClose, initialView }) {
  const [telemetry, setTelemetry] = useState({
    position: { north: 0, east: 0, down: 0 },
    altitude: 0, battery: 0, in_air: false, armed: false,
  });
  const [activeView, setActiveView] = useState(initialView || 'front');
  const keysRef = useRef(new Set());
  const [activeKeys, setActiveKeys] = useState(new Set());
  const sendIntervalRef = useRef(null);
  const lidarCanvasRef = useRef(null);

  const buildCmd = useCallback((keys) => {
    let forward = 0, right = 0, down = 0, yaw_rate = 0;
    if (keys.has('w')) forward = SPEED;
    if (keys.has('s')) forward = -SPEED;
    if (keys.has('a')) right = -SPEED;
    if (keys.has('d')) right = SPEED;
    if (keys.has(' ')) down = DOWN_UP;
    if (keys.has('shift')) down = DOWN_DN;
    if (keys.has('q')) yaw_rate = -YAW_SPEED;
    if (keys.has('e')) yaw_rate = YAW_SPEED;
    return { forward, right, down, yaw_rate };
  }, []);

  const sendStop = useCallback(() => {
    if (socket) socket.emit('velocity_control', { forward: 0, right: 0, down: 0, yaw_rate: 0 });
  }, [socket]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') { sendStop(); onClose(); return; }
      // 数字键切换视角: 1=前 2=后 3=左 4=右 5=下
      const viewMap = { '1': 'front', '2': 'rear', '3': 'left', '4': 'right', '5': 'down' };
      if (viewMap[e.key]) { setActiveView(viewMap[e.key]); return; }
      const k = e.key === ' ' ? ' ' : e.key === 'Shift' ? 'shift' : e.key.toLowerCase();
      if (['w','a','s','d',' ','shift','q','e'].includes(k)) {
        e.preventDefault();
        keysRef.current.add(k);
        setActiveKeys(new Set(keysRef.current));
      }
    };
    const handleKeyUp = (e) => {
      const k = e.key === ' ' ? ' ' : e.key === 'Shift' ? 'shift' : e.key.toLowerCase();
      keysRef.current.delete(k);
      setActiveKeys(new Set(keysRef.current));
      if (keysRef.current.size === 0) sendStop();
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => { window.removeEventListener('keydown', handleKeyDown); window.removeEventListener('keyup', handleKeyUp); };
  }, [onClose, sendStop]);

  useEffect(() => {
    sendIntervalRef.current = setInterval(() => {
      if (keysRef.current.size > 0 && socket) socket.emit('velocity_control', buildCmd(keysRef.current));
    }, SEND_INTERVAL);
    return () => { clearInterval(sendIntervalRef.current); sendStop(); };
  }, [socket, buildCmd, sendStop]);

  useEffect(() => {
    if (!socket) return;
    const handler = (data) => setTelemetry(data);
    socket.on('telemetry', handler);
    const poll = setInterval(() => socket.emit('get_telemetry'), TELEMETRY_POLL);
    socket.emit('get_telemetry');
    return () => { socket.off('telemetry', handler); clearInterval(poll); };
  }, [socket]);

  useEffect(() => {
    const canvas = lidarCanvasRef.current;
    if (!canvas || !sensorLidar) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height, cx = w / 2, cy = h / 2;
    const maxRange = sensorLidar.range_max || 10;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = 'rgba(0,0,0,0.85)';
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(0,212,255,0.12)';
    ctx.lineWidth = 0.5;
    for (let r = 1; r <= 3; r++) {
      ctx.beginPath();
      ctx.arc(cx, cy, (r / 3) * (w / 2 - 8), 0, Math.PI * 2);
      ctx.stroke();
    }
    const ranges = sensorLidar.ranges || [];
    const angleMin = sensorLidar.angle_min || 0;
    const angleInc = sensorLidar.angle_increment || 0;
    const rangeMin = sensorLidar.range_min || 0;
    const scale = (w / 2 - 8) / maxRange;
    for (let i = 0; i < ranges.length; i++) {
      const dist = ranges[i];
      if (dist < rangeMin || dist > maxRange || !isFinite(dist)) continue;
      const angle = angleMin + i * angleInc;
      const px = cx + Math.sin(-angle) * dist * scale;
      const py = cy - Math.cos(angle) * dist * scale;
      const t = Math.min(dist / maxRange, 1);
      ctx.fillStyle = 'rgb(' + Math.round(255*(1-t)) + ',' + Math.round(255*t) + ',0)';
      ctx.fillRect(px - 1.5, py - 1.5, 3, 3);
    }
    ctx.fillStyle = CYAN;
    ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = CYAN; ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(cx, cy - 6); ctx.lineTo(cx, cy - 18);
    ctx.moveTo(cx - 5, cy - 13); ctx.lineTo(cx, cy - 18); ctx.lineTo(cx + 5, cy - 13);
    ctx.stroke();
  }, [sensorLidar]);

  const pressKey = (k) => { keysRef.current.add(k); setActiveKeys(new Set(keysRef.current)); };
  const releaseKey = (k) => { keysRef.current.delete(k); setActiveKeys(new Set(keysRef.current)); if (keysRef.current.size === 0) sendStop(); };

  const frontImg = sensorCameras?.front?.image;
  const rearImg = sensorCameras?.rear?.image;
  const leftImg = sensorCameras?.left?.image;
  const rightImg = sensorCameras?.right?.image;
  const downImg = sensorCameras?.down?.image;
  const pos = telemetry.position || { north: 0, east: 0, down: 0 };
  const battPct = telemetry.battery != null ? Math.round(telemetry.battery) : '--';

  // 当前主画面
  const viewImages = { front: frontImg, rear: rearImg, left: leftImg, right: rightImg, down: downImg };
  const viewLabels = { front: '▲ FRONT', rear: '▼ REAR', left: '◀ LEFT', right: '▶ RIGHT', down: '⊙ DOWN' };
  const mainImg = viewImages[activeView];

  // PiP: 显示除当前视角外的其他4个
  const pipViews = Object.keys(viewImages).filter(v => v !== activeView);

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999, background: '#000', cursor: 'crosshair', fontFamily: 'monospace', overflow: 'hidden' }}>
      {/* Full-screen active camera */}
      {mainImg && (
        <img src={'data:image/jpeg;base64,' + mainImg} alt={activeView}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
      )}
      {!mainImg && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'rgba(0,212,255,0.3)', fontSize: 16, fontFamily: 'monospace' }}>
          NO SIGNAL — {viewLabels[activeView]}
        </div>
      )}

      {/* Active view badge */}
      <div style={{ position: 'absolute', top: 52, left: '50%', transform: 'translateX(-50%)', zIndex: 4,
        background: 'rgba(0,0,0,0.7)', borderRadius: 4, padding: '2px 10px',
        fontFamily: 'monospace', fontSize: 11, color: CYAN, letterSpacing: 2 }}>
        {viewLabels[activeView]}
      </div>

      {/* Scan line overlay */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.06) 2px, rgba(0,0,0,0.06) 4px)',
        zIndex: 1,
      }} />

      {/* Corner brackets */}
      <CornerBracket top={16} left={16} />
      <CornerBracket top={16} right={16} />
      <CornerBracket bottom={16} left={16} />
      <CornerBracket bottom={16} right={16} />

      {/* Center crosshair */}
      <svg width="80" height="80" viewBox="0 0 80 80" style={{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%,-50%)', pointerEvents: 'none', opacity: 0.6, zIndex: 2,
      }}>
        <circle cx="40" cy="40" r="18" stroke={CYAN} strokeWidth="1.5" fill="none" />
        <line x1="40" y1="0" x2="40" y2="28" stroke={CYAN} strokeWidth="1.2" />
        <line x1="40" y1="52" x2="40" y2="80" stroke={CYAN} strokeWidth="1.2" />
        <line x1="0" y1="40" x2="28" y2="40" stroke={CYAN} strokeWidth="1.2" />
        <line x1="52" y1="40" x2="80" y2="40" stroke={CYAN} strokeWidth="1.2" />
        <circle cx="40" cy="40" r="2.5" fill={CYAN} />
      </svg>

      {/* HUD Top Bar */}
      <div style={{
        position: 'absolute', top: 0, left: 0, right: 0, zIndex: 3,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: 16, padding: '12px 24px', pointerEvents: 'none',
      }}>
        <span style={{ background: BADGE_BG, borderRadius: 6, padding: '4px 10px', fontFamily: 'monospace', fontSize: 13, color: '#fff' }}>
          {telemetry.armed ? '🟢 ARMED' : '🔴 DISARM'}
        </span>
        <span style={{ background: BADGE_BG, borderRadius: 6, padding: '4px 10px', fontFamily: 'monospace', fontSize: 13, color: '#fff' }}>
          {telemetry.in_air ? '✈ FLIGHT' : '🅿 GND'}
        </span>
        <span style={{ background: BADGE_BG, borderRadius: 6, padding: '4px 10px', fontFamily: 'monospace', fontSize: 13, color: '#fff' }}>
          🔋 {battPct}%
        </span>
        <button onClick={() => { sendStop(); onClose(); }} style={{
          pointerEvents: 'auto', background: 'rgba(255,60,60,0.7)', border: 'none',
          color: '#fff', borderRadius: 6, padding: '4px 14px', fontFamily: 'monospace',
          fontSize: 13, cursor: 'pointer',
        }}>
          ✖ CLOSE
        </button>
      </div>

      {/* Left side - Altitude */}
      <div style={{
        position: 'absolute', left: 24, top: '50%', transform: 'translateY(-50%)', zIndex: 3, pointerEvents: 'none',
        ...{ background: GLASS_BG, border: '1px solid ' + GLASS_BORDER, backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', borderRadius: 8, padding: '10px 14px', color: CYAN, fontFamily: 'monospace' },
      }}>
        <div style={{ fontSize: 10, opacity: 0.6, marginBottom: 4 }}>ALT</div>
        <div style={{ fontSize: 22, fontWeight: 'bold' }}>{telemetry.altitude != null ? telemetry.altitude.toFixed(1) : '0.0'}</div>
        <div style={{ fontSize: 10, opacity: 0.6 }}>m</div>
      </div>

      {/* Right side - Position NED */}
      <div style={{
        position: 'absolute', right: 24, top: '50%', transform: 'translateY(-50%)', zIndex: 3, pointerEvents: 'none',
        background: GLASS_BG, border: '1px solid ' + GLASS_BORDER, backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)', borderRadius: 8, padding: '10px 14px', color: CYAN, fontFamily: 'monospace',
      }}>
        <div style={{ fontSize: 10, opacity: 0.6, marginBottom: 4 }}>POS NED</div>
        <div style={{ fontSize: 13 }}>N {pos.north != null ? pos.north.toFixed(2) : '0.00'}</div>
        <div style={{ fontSize: 13 }}>E {pos.east != null ? pos.east.toFixed(2) : '0.00'}</div>
        <div style={{ fontSize: 13 }}>D {pos.down != null ? pos.down.toFixed(2) : '0.00'}</div>
      </div>

      {/* Bottom area container */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 3,
        display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
        padding: '0 20px 16px 20px', pointerEvents: 'none',
      }}>
        {/* Bottom-left: PiP cameras (click to switch) */}
        <div style={{ display: 'flex', gap: 6, pointerEvents: 'auto' }}>
          {pipViews.map(v => (
            <div key={v} onClick={() => setActiveView(v)} style={{ cursor: 'pointer' }}>
              <PiPCamera image={viewImages[v]} label={viewLabels[v]} />
            </div>
          ))}
        </div>

        {/* Bottom-center: Control pad + hint */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, pointerEvents: 'auto' }}>
          <div style={{ display: 'flex', gap: 4, alignItems: 'end' }}>
            {/* WASD grid */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
              <div style={{ display: 'flex', gap: 4 }}>
                <div style={{ width: 48, height: 48 }} />
                <CtrlBtn label="W" active={activeKeys.has('w')} onDown={() => pressKey('w')} onUp={() => releaseKey('w')} />
                <div style={{ width: 48, height: 48 }} />
              </div>
              <div style={{ display: 'flex', gap: 4 }}>
                <CtrlBtn label="A" active={activeKeys.has('a')} onDown={() => pressKey('a')} onUp={() => releaseKey('a')} />
                <CtrlBtn label="S" active={activeKeys.has('s')} onDown={() => pressKey('s')} onUp={() => releaseKey('s')} />
                <CtrlBtn label="D" active={activeKeys.has('d')} onDown={() => pressKey('d')} onUp={() => releaseKey('d')} />
              </div>
            </div>
            {/* UP/DN buttons */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginLeft: 8 }}>
              <CtrlBtn label="UP" active={activeKeys.has(' ')} onDown={() => pressKey(' ')} onUp={() => releaseKey(' ')} wide />
              <CtrlBtn label="DN" active={activeKeys.has('shift')} onDown={() => pressKey('shift')} onUp={() => releaseKey('shift')} wide />
            </div>
          </div>
          <div style={{ fontSize: 10, color: 'rgba(0,212,255,0.5)', pointerEvents: 'none', textAlign: 'center', whiteSpace: 'nowrap' }}>
            W/A/S/D 移动 · SPACE ↑ · SHIFT ↓ · Q/E 旋转 · 1-5 切换视角 · ESC 退出
          </div>
        </div>

        {/* Bottom-right: LiDAR mini radar */}
        <div style={{ pointerEvents: 'none' }}>
          <canvas
            ref={lidarCanvasRef}
            width={160}
            height={160}
            style={{
              width: 160, height: 160, borderRadius: 8,
              border: '1px solid ' + GLASS_BORDER,
            }}
          />
        </div>
      </div>
    </div>
  );
}
