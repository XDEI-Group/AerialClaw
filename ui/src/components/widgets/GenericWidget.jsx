import React from 'react';

const cardStyle = {
  background: '#1e1e2e',
  border: '1px solid #313244',
  borderRadius: 12,
  padding: 12,
  minHeight: 150,
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
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
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: '2px 0',
  borderBottom: '1px solid #1e1e2e',
  fontSize: 12,
};

const keyStyle = {
  color: '#6c7086',
  fontFamily: 'monospace',
  flexShrink: 0,
  marginRight: 8,
};

const numStyle = {
  color: '#cdd6f4',
  fontFamily: 'monospace',
  fontWeight: 700,
  textAlign: 'right',
};

const strStyle = {
  color: '#a6adc8',
  textAlign: 'right',
  wordBreak: 'break-all',
  maxWidth: '60%',
};

function BoolDot({ val }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: val ? '#a6e3a1' : '#f38ba8',
        marginRight: 4,
        verticalAlign: 'middle',
      }}
    />
  );
}

function renderValue(v) {
  if (v === null || v === undefined) {
    return <span style={{ color: '#585b70' }}>null</span>;
  }
  if (typeof v === 'boolean') {
    return (
      <span>
        <BoolDot val={v} />
        <span style={{ color: v ? '#a6e3a1' : '#f38ba8' }}>{String(v)}</span>
      </span>
    );
  }
  if (typeof v === 'number') {
    return <span style={numStyle}>{Number.isInteger(v) ? v : v.toFixed(4)}</span>;
  }
  if (Array.isArray(v)) {
    return <span style={{ color: '#6c7086', fontSize: 11 }}>[{v.length} items]</span>;
  }
  if (typeof v === 'object') {
    return <span style={{ color: '#6c7086', fontSize: 11 }}>{'{…}'}</span>;
  }
  return <span style={strStyle}>{String(v)}</span>;
}

export default function GenericWidget({ data = {}, title = 'Data' }) {
  const entries = Object.entries(data);

  return (
    <div style={cardStyle}>
      <p style={titleStyle}>{title}</p>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {entries.length === 0 ? (
          <div style={{ color: '#585b70', fontSize: 12, padding: '8px 0' }}>无数据</div>
        ) : (
          entries.map(([k, v]) => (
            <div key={k} style={rowStyle}>
              <span style={keyStyle}>{k}</span>
              {renderValue(v)}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
