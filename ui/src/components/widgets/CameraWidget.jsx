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

const placeholderStyle = {
  flex: 1,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: '#585b70',
  fontSize: 13,
};

const metaStyle = {
  display: 'flex',
  gap: 12,
  fontSize: 11,
  color: '#6c7086',
};

const metaValueStyle = {
  color: '#a6adc8',
  fontWeight: 600,
};

export default function CameraWidget({ data = {}, title = 'Camera' }) {
  const { image, width, height, fps } = data;

  return (
    <div style={cardStyle}>
      <p style={titleStyle}>{title}</p>
      {image ? (
        <img
          src={`data:image/jpeg;base64,${image}`}
          alt="camera feed"
          style={{ width: '100%', borderRadius: 6, objectFit: 'cover' }}
        />
      ) : (
        <div style={placeholderStyle}>等待图像...</div>
      )}
      {(width || height || fps) && (
        <div style={metaStyle}>
          {(width && height) && (
            <span>分辨率 <span style={metaValueStyle}>{width}×{height}</span></span>
          )}
          {fps != null && (
            <span>FPS <span style={metaValueStyle}>{fps}</span></span>
          )}
        </div>
      )}
    </div>
  );
}
