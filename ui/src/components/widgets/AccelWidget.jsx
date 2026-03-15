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

const AXES = [
  { key: 'x', alt: 'accel_x', label: 'X', color: '#f38ba8' },
  { key: 'y', alt: 'accel_y', label: 'Y', color: '#a6e3a1' },
  { key: 'z', alt: 'accel_z', label: 'Z', color: '#89b4fa' },
];

function AxisRow({ label, value, color }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
      <span
        style={{
          fontSize: 11,
          fontWeight: 700,
          color,
          width: 16,
          textAlign: 'center',
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 22,
          fontWeight: 700,
          fontFamily: 'monospace',
          color,
        }}
      >
        {value != null ? Number(value).toFixed(3) : '—'}
      </span>
      <span style={{ fontSize: 11, color: '#6c7086' }}>m/s²</span>
    </div>
  );
}

export default function AccelWidget({ data = {}, title = 'Accelerometer' }) {
  return (
    <div style={cardStyle}>
      <p style={titleStyle}>{title}</p>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6 }}>
        {AXES.map(({ key, alt, label, color }) => (
          <AxisRow
            key={key}
            label={label}
            value={data[key] ?? data[alt]}
            color={color}
          />
        ))}
      </div>
    </div>
  );
}
