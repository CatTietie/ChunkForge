import type { WSEvent } from '../types';

interface Props {
  events: WSEvent[];
  connected: boolean;
}

const EVENT_LABELS: Record<string, string> = {
  node_joined: '节点加入',
  node_removed: '节点移除',
  node_crashed: '节点宕机',
  node_resurrected: '节点恢复',
  file_uploaded: '文件上传',
  file_deleted: '文件删除',
  shard_written: '分片写入',
  shard_deleted: '分片删除',
  repair_started: '修复开始',
  repair_progress: '修复进度',
  repair_completed: '修复完成',
  repair_failed: '修复失败',
  partition_detected: '分区检测',
  partition_healed: '分区恢复',
  term_incremented: 'Term递增',
  rebalance_started: '再平衡开始',
  rebalance_progress: '再平衡进度',
  rebalance_completed: '再平衡完成',
  rebalance_paused: '再平衡暂停',
};

const EVENT_COLORS: Record<string, string> = {
  node_crashed: '#ef4444',
  repair_failed: '#ef4444',
  repair_started: '#f59e0b',
  repair_progress: '#f59e0b',
  repair_completed: '#22c55e',
  file_uploaded: '#3b82f6',
  node_joined: '#22c55e',
  node_resurrected: '#22c55e',
  rebalance_started: '#8b5cf6',
  rebalance_progress: '#8b5cf6',
  rebalance_completed: '#22c55e',
  rebalance_paused: '#f59e0b',
};

export function EventLog({ events, connected }: Props) {
  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 8 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
        实时事件日志
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: connected ? '#22c55e' : '#ef4444',
          display: 'inline-block',
        }} />
      </h3>
      <div style={{ maxHeight: 250, overflow: 'auto', fontSize: 12, fontFamily: 'monospace' }}>
        {events.length === 0 && (
          <div style={{ color: '#6b7280' }}>等待事件...</div>
        )}
        {events.map((e, i) => (
          <div key={i} style={{ padding: '2px 0', borderBottom: '1px solid #f3f4f6' }}>
            <span style={{ color: '#6b7280' }}>
              {new Date(e.timestamp).toLocaleTimeString()}
            </span>{' '}
            <span style={{ color: EVENT_COLORS[e.type] || '#374151', fontWeight: 500 }}>
              [{EVENT_LABELS[e.type] || e.type}]
            </span>{' '}
            <span style={{ color: '#4b5563' }}>
              {JSON.stringify(e.payload).slice(0, 80)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
