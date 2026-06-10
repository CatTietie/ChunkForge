import { useState } from 'react';
import type { NodeInfo } from '../types';
import { addNode, crashNode, recoverNode, removeNode, triggerRebalance } from '../api/client';

interface Props {
  nodes: NodeInfo[];
  onRefresh: () => void;
}

export function NodeControls({ nodes, onRefresh }: Props) {
  const [newNodeId, setNewNodeId] = useState('');

  const handleAdd = async () => {
    const id = newNodeId.trim() || `node-${nodes.length}`;
    await addNode({
      node_id: id,
      address: `http://${id}:9000`,
      status: 'online',
      shard_count: 0,
      capacity_bytes: 1073741824,
      used_bytes: 0,
    });
    setNewNodeId('');
    onRefresh();
  };

  const handleCrash = async (nodeId: string) => {
    await crashNode(nodeId);
    onRefresh();
  };

  const handleRecover = async (nodeId: string) => {
    await recoverNode(nodeId);
    onRefresh();
  };

  const handleRemove = async (nodeId: string) => {
    if (!confirm(`确认移除 ${nodeId}？`)) return;
    await removeNode(nodeId);
    onRefresh();
  };

  const handleRebalance = async () => {
    await triggerRebalance();
    onRefresh();
  };

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 8 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>节点控制</h3>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input
          value={newNodeId}
          onChange={(e) => setNewNodeId(e.target.value)}
          placeholder="节点ID (可选)"
          style={{ fontSize: 12, padding: '2px 6px' }}
        />
        <button onClick={handleAdd} style={{ fontSize: 12 }}>添加节点</button>
        <button onClick={handleRebalance} style={{ fontSize: 12, color: '#8b5cf6' }}>触发再平衡</button>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {nodes.map((n) => (
          <div key={n.node_id} style={{
            padding: '4px 8px', borderRadius: 4, fontSize: 11,
            background: n.status === 'online' ? '#dcfce7' : n.status === 'crashed' ? '#fee2e2' : '#f3f4f6',
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <span style={{ fontWeight: 500 }}>{n.node_id}</span>
            {n.status === 'online' && (
              <button onClick={() => handleCrash(n.node_id)} style={{ fontSize: 10, color: '#ef4444' }}>
                宕机
              </button>
            )}
            {n.status === 'crashed' && (
              <button onClick={() => handleRecover(n.node_id)} style={{ fontSize: 10, color: '#22c55e' }}>
                恢复
              </button>
            )}
            <button onClick={() => handleRemove(n.node_id)} style={{ fontSize: 10, color: '#6b7280' }}>
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
