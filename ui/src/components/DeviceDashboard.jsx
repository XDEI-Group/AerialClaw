/**
 * DeviceDashboard.jsx — 动态设备仪表板
 *
 * 根据设备 capabilities 自动选择 Widget 渲染。
 * 未知能力用 GenericWidget 兜底。
 */
import { useMemo } from 'react'
import CameraWidget from './widgets/CameraWidget'
import GpsWidget from './widgets/GpsWidget'
import BatteryWidget from './widgets/BatteryWidget'
import LidarWidget from './widgets/LidarWidget'
import AccelWidget from './widgets/AccelWidget'
import GenericWidget from './widgets/GenericWidget'

// 能力 → Widget 映射
const WIDGET_MAP = {
  camera:        { component: CameraWidget, title: '摄像头', dataKey: 'camera' },
  gps:           { component: GpsWidget,    title: 'GPS 定位', dataKey: 'gps' },
  battery:       { component: BatteryWidget, title: '电池', dataKey: 'battery' },
  lidar:         { component: LidarWidget,  title: 'LiDAR 雷达', dataKey: 'lidar' },
  accelerometer: { component: AccelWidget,  title: '加速度计', dataKey: 'accel' },
}

// 从 deviceState 中提取 Widget 需要的数据
function extractData(state, sensorData, dataKey) {
  // 优先从 sensorData 取，再从 state 取
  if (sensorData && sensorData[dataKey]) return sensorData[dataKey]
  // GPS: 从 state 的 latitude/longitude 组装
  if (dataKey === 'gps') {
    return { latitude: state.latitude, longitude: state.longitude, altitude: state.altitude }
  }
  // Battery: 从 state 的 battery 字段取
  if (dataKey === 'battery') {
    return { battery: state.battery, charging: state.charging || state.status === 'charging' }
  }
  // Accel: 从 state 取
  if (dataKey === 'accel') {
    return { x: state.accel_x || state.x, y: state.accel_y || state.y, z: state.accel_z || state.z }
  }
  return state
}

export default function DeviceDashboard({ capabilities = [], deviceState = {}, sensorData = {} }) {
  // 根据 capabilities 确定要渲染的 Widget
  const widgets = useMemo(() => {
    const result = []
    const matched = new Set()

    for (const cap of capabilities) {
      const capLower = cap.toLowerCase()
      const mapping = WIDGET_MAP[capLower]
      if (mapping && !matched.has(capLower)) {
        matched.add(capLower)
        result.push({ ...mapping, capability: capLower })
      }
    }

    return result
  }, [capabilities])

  if (!capabilities.length) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: '#64748b' }}>
        设备暂无已知能力，等待建档完成...
      </div>
    )
  }

  return (
    <div>
      {/* Widget 网格 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
        gap: 12,
        marginBottom: 12,
      }}>
        {widgets.map(w => {
          const Widget = w.component
          const data = extractData(deviceState, sensorData, w.dataKey)
          return (
            <div key={w.capability} style={{
              background: '#111827',
              borderRadius: 10,
              border: '1px solid #1e293b',
              overflow: 'hidden',
            }}>
              <div style={{
                padding: '6px 12px',
                borderBottom: '1px solid #1e293b',
                fontSize: 12,
                color: '#94a3b8',
                fontWeight: 600,
              }}>
                {w.title}
              </div>
              <div style={{ padding: 10 }}>
                <Widget data={data} title={w.title} />
              </div>
            </div>
          )
        })}
      </div>

      {/* 原始数据（始终显示） */}
      <div style={{
        background: '#111827',
        borderRadius: 10,
        border: '1px solid #1e293b',
        overflow: 'hidden',
      }}>
        <div style={{
          padding: '6px 12px',
          borderBottom: '1px solid #1e293b',
          fontSize: 12,
          color: '#94a3b8',
          fontWeight: 600,
        }}>
          设备状态（原始数据）
        </div>
        <div style={{ padding: 10 }}>
          <GenericWidget data={deviceState} title="设备状态" />
        </div>
      </div>
    </div>
  )
}
