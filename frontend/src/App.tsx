import { TopologyGraph } from './components/TopologyGraph';
import { ShardHeatmap } from './components/ShardHeatmap';
import { EventLog } from './components/EventLog';
import { FileManager } from './components/FileManager';
import { NodeControls } from './components/NodeControls';
import { useCluster } from './hooks/useCluster';
import { useWebSocket } from './hooks/useWebSocket';
import { crashNode, recoverNode } from './api/client';

export default function App() {
  const { cluster, files, loading, refresh } = useCluster();
  const wsUrl = `ws://${window.location.host}/ws/events`;
  const { events, connected } = useWebSocket(wsUrl);

  const handleCrash = async (nodeId: string) => {
    await crashNode(nodeId);
    refresh();
  };

  const handleRecover = async (nodeId: string) => {
    await recoverNode(nodeId);
    refresh();
  };

  if (loading || !cluster) {
    return <div style={{ padding: 20, textAlign: 'center' }}>加载集群状态中...</div>;
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 16, fontFamily: 'system-ui, sans-serif' }}>
      <header style={{ marginBottom: 16, borderBottom: '1px solid #e5e7eb', paddingBottom: 8 }}>
        <h1 style={{ margin: 0, fontSize: 20 }}>ChunkForge 分布式存储演示</h1>
        <p style={{ margin: '4px 0 0', fontSize: 12, color: '#6b7280' }}>
          Reed-Solomon (4+2) 纠删码 | {cluster.online_nodes}/{cluster.total_nodes} 节点在线 | {files.length} 文件
        </p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <TopologyGraph nodes={cluster.nodes} onCrash={handleCrash} onRecover={handleRecover} />
        <ShardHeatmap files={files} nodes={cluster.nodes} />
        <FileManager files={files} onRefresh={refresh} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <NodeControls nodes={cluster.nodes} onRefresh={refresh} />
          <EventLog events={events} connected={connected} />
        </div>
      </div>
    </div>
  );
}
