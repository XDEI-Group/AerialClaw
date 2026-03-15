import React, { useState, useEffect, useRef } from 'react';

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

const rowStyle = {
  display: 'flex',
  flexDirection: 'column',
  gap: 2,
};

const labelStyle = {
  fontSize: 10,
  color: '#6c7086',
  textTransform: 'uppercase',
  letterSpacing: 0.8,
};

function CoordValue({ value, flash }) {
  const [lit, setLit] = useState(false);
  const prev = useRef(value);

  useEffect(() => {
    if (prev.current !== value && flash) {
      setLit(true);
      const t = setTimeout(() => setLit(false), 400);
      prev.current = value;
      return () => clearTimeout(t);
    }
  }, [value, flash]);

  return (
    <span
      style={{
        fontSize: 20,
        fontWeight: 700,
        fontFamily: 'monospace',
        color: lit ? '#89dceb' : '#cdd6f4',
        transition: 'color 0.3s',
      }}
    >
      {value != null ? Number(value).toFixed(6) : '—'}
    </span>
  );
}

export default function GpsWidget({ data = {}, title = 'GPS' }) {
  const { latitude, longitude, altitude } = data;

  return (
    <div style={cardStyle}>
      <p style={titleStyle}>{title}</p>
      <div style={rowStyle}>
        <span style={labelStyle}>纬度</span>
        <CoordValue value={latitude} flash />
      </div>
      <div style={rowStyle}>
        <span style={labelStyle}>经度</span>
        <CoordValue value={longitude} flash />
      </div>
      {altitude != null && (
        <div style={rowStyle}>
          <span style={labelStyle}>海拔 (m)</span>
          <CoordValue value={altitude} flash />
        </div>
      )}
    </div>
  );
}
