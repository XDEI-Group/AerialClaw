import React from 'react';

const cardStyle = {
  background: '#1e1e2e',
  border: '1px solid #313244',
  borderRadius: 12,
  padding: 12,
  minHeight: 150,
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
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
};

function barColor(pct) {
  if (pct > 60) return '#a6e3a1';
  if (pct >= 30) return '#f9e2af';
  return '#f38ba8';
}

export default function BatteryWidget({ data = {}, title = 'Battery' }) {
  const pct = data.battery != null ? Math.max(0, Math.min(100, data.battery)) : null;
  const charging = data.charging === true;
  const color = pct != null ? barColor(pct) : '#585b70';

  return (
    <div style={cardStyle}>
      <p style={titleStyle}>{title}</p>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 14 }}>
        {/* Progress bar */}
        <div style={{ flex: 1 }}>
          <div
            style={{
              background: '#313244',
              borderRadius: 6,
              height: 14,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: pct != null ? `${pct}%` : '0%',
                height: '100%',
                background: color,
                borderRadius: 6,
                transition: 'width 0.5s ease, background 0.5s ease',
              }}
            />
          </div>
        </div>
        {/* Percentage */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span
            style={{
              fontSize: 28,
              fontWeight: 700,
              fontFamily: 'monospace',
              color: color,
              minWidth: 56,
              textAlign: 'right',
            }}
          >
            {pct != null ? `${pct}%` : '—'}
          </span>
          {charging && (
            <span style={{ fontSize: 20, color: '#f9e2af' }} title="充电中">
              ⚡
            </span>
          )}
        </div>
      </div>
      <div style={{ fontSize: 11, color: '#6c7086' }}>
        {charging ? '充电中' : pct != null ? (pct > 20 ? '放电中' : '电量不足') : '无数据'}
      </div>
    </div>
  );
}
