export interface ShardLocation {
  shard_index: number;
  node_id: string;
  shard_id: string;
  checksum_sha256: string;
  size_bytes: number;
  role: 'data' | 'parity';
}

export interface FileMeta {
  file_id: string;
  name: string;
  size: number;
  status: 'healthy' | 'degraded' | 'repairing' | 'lost';
  upload_time: string;
  shard_count: number;
  shards?: ShardLocation[];
}

export interface NodeInfo {
  node_id: string;
  address: string;
  status: 'online' | 'offline' | 'crashed' | 'draining';
  shard_count: number;
  capacity_bytes: number;
  used_bytes: number;
  last_heartbeat: string | null;
  joined_at: string;
  term_acknowledged: number;
}

export interface ClusterStatus {
  nodes: NodeInfo[];
  files_count: number;
  online_nodes: number;
  total_nodes: number;
}

export interface WSEvent {
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
  source?: string;
}
