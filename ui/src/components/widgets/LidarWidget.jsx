import React, { useRef, useEffect } from 'react';

const cardStyle = {
  background: '#1e1e2e',
  border: '1px solid #313244',
  borderRadius: 12,
  padding: 12,
  minHeight: 150,
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  alignItems: 'center',
};

const titleStyle = {
  color: '#cdd6f4',
  fontSize: 12,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 1,
  borderBottom: '1px solid #313244',
  paddingBottom: 6,
  margin: 0,
  width: '100%',
};

const placeholderStyle = {
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: '#585b70',
  fontSize: 13,
  height: 200,
};

const SIZE = 200;
const CENTER = SIZE / 2;
const RADIUS = SIZE / 2 - 10;

function drawRadar(canvas, ranges, angleMin, angleMax) {
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, SIZE, SIZE);

  // Background
  ctx.fillStyle = '#11111b';
  ctx.beginPath();
  ctx.arc(CENTER, CENTER, RADIUS, 0, Math.PI * 2);
  ctx.fill();

  // Grid rings
  ctx.strokeStyle = '#313244';
  ctx.lineWidth = 1;
  for (let r = 1; r <= 3; r++) {
    ctx.beginPath();
    ctx.arc(CENTER, CENTER, (RADIUS / 3) * r, 0, Math.PI * 2);
    ctx.stroke();
  }

  // Grid lines
  for (let i = 0; i < 6; i++) {
    const a = (i * Math.PI) / 3;
    ctx.beginPath();
    ctx.moveTo(CENTER, CENTER);
    ctx.lineTo(CENTER + Math.cos(a) * RADIUS, CENTER + Math.sin(a) * RADIUS);
    ctx.stroke();
  }

  if (!ranges || ranges.length === 0) return;

  const count = ranges.length;
  const maxRange = Math.max(...ranges.filter(Number.isFinite), 1);

  // Sweep fill
  ctx.beginPath();
  let started = false;
  for (let i = 0; i < count; i++) {
    const angle = angleMin + ((angleMax - angleMin) * i) / (count - 1);
    const r = Number.isFinite(ranges[i]) ? ranges[i] : maxRange;
    const dist = Math.min(r / maxRange, 1) * RADIUS;
    // Rotate so 0° points up (subtract π/2)
    const px = CENTER + Math.cos(angle - Math.PI / 2) * dist;
    const py = CENTER + Math.sin(angle - Math.PI / 2) * dist;
    if (!started) {
      ctx.moveTo(px, py);
      started = true;
    } else {
      ctx.lineTo(px, py);
    }
  }
  ctx.closePath();
  ctx.fillStyle = 'rgba(137, 220, 235, 0.15)';
  ctx.fill();
  ctx.strokeStyle = '#89dceb';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Points
  for (let i = 0; i < count; i++) {
    if (!Number.isFinite(ranges[i])) continue;
    const angle = angleMin + ((angleMax - angleMin) * i) / (count - 1);
    const dist = Math.min(ranges[i] / maxRange, 1) * RADIUS;
    const px = CENTER + Math.cos(angle - Math.PI / 2) * dist;
    const py = CENTER + Math.sin(angle - Math.PI / 2) * dist;
    ctx.beginPath();
    ctx.arc(px, py, 1.5, 0, Math.PI * 2);
    ctx.fillStyle = '#89dceb';
    ctx.fill();
  }

  // Center dot
  ctx.beginPath();
  ctx.arc(CENTER, CENTER, 3, 0, Math.PI * 2);
  ctx.fillStyle = '#cba6f7';
  ctx.fill();
}

export default function LidarWidget({ data = {}, title = 'LiDAR' }) {
  const canvasRef = useRef(null);
  const { ranges, angle_min = -Math.PI, angle_max = Math.PI } = data;

  useEffect(() => {
    if (canvasRef.current) {
      drawRadar(canvasRef.current, ranges, angle_min, angle_max);
    }
  }, [ranges, angle_min, angle_max]);

  const hasData = ranges && ranges.length > 0;

  return (
    <div style={cardStyle}>
      <p style={titleStyle}>{title}</p>
      {hasData ? (
        <canvas
          ref={canvasRef}
          width={SIZE}
          height={SIZE}
          style={{ borderRadius: 8 }}
        />
      ) : (
        <div style={placeholderStyle}>等待数据...</div>
      )}
    </div>
  );
}
