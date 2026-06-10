# 节点通信协议规范

## 1. 心跳协议

### Node → Coordinator
```
POST /internal/heartbeat
Interval: 1000ms
Timeout: 3000ms (Coordinator声明节点死亡)

Request:
{
  "node_id": "node-0",
  "term": 42,
  "shard_count": 15,
  "disk_usage_bytes": 1048576,
  "timestamp": "2026-06-08T12:00:00.000Z"
}

Response:
{
  "ack": true,
  "current_term": 42,
  "commands": []  // 可选: ["inventory_report"]
}
```

### 规则
- 节点收到更高term时更新本地term
- Coordinator 3s未收到心跳则标记节点CRASHED
- 节点无法连接Coordinator时继续服务读请求

## 2. 分片传输协议

### 写入分片
```
PUT /shards/{shard_id}
Headers:
  X-File-Id: {uuid}
  X-Shard-Index: {0-5}
  X-Shard-Size: {bytes}
  X-Checksum-SHA256: {hex}
  X-Reed-Solomon-Role: data|parity
  Content-Type: application/octet-stream
Body: <raw bytes>

Response: 201 Created
{
  "shard_id": "abc123_2",
  "stored": true,
  "checksum_verified": true,
  "size_bytes": 262144
}
```

### 读取分片
```
GET /shards/{shard_id}

Response: 200 OK
Headers:
  X-Shard-Id: abc123_2
  X-Checksum-SHA256: {hex}
  X-Shard-Size: {bytes}
Body: <raw bytes>
```

### 删除分片
```
DELETE /shards/{shard_id}

Response: 200 OK
{"shard_id": "abc123_2", "deleted": true}
```

### 健康检查
```
GET /health

Response: 200 OK
{
  "node_id": "node-0",
  "status": "online",
  "shard_count": 15,
  "shards": ["file1_0", "file1_3", ...],
  "disk_usage_bytes": 1048576
}
```

## 3. 修复协调流程

修复由 Coordinator 驱动，节点为被动响应者:

```
Coordinator                   Survivor-A          Target-X
    │                              │                  │
    ├── GET /shards/file_0 ───────►│                  │
    │◄── 200 + data ──────────────┤                  │
    ├── GET /shards/file_1 ───────►│                  │
    │◄── 200 + data ──────────────┤                  │
    │  (重复获取k=4个分片)          │                  │
    │                              │                  │
    │  [RS reconstruct locally]    │                  │
    │                              │                  │
    ├── PUT /shards/file_2 ────────────────────────►│
    │◄── 201 Created ─────────────────────────────┤│
    │                              │                  │
    │  [update metadata]           │                  │
```

## 4. 节点注册

```
POST /internal/nodes/register
{
  "node_id": "node-6",
  "address": "http://node-6:9000",
  "status": "online",
  "shard_count": 0,
  "capacity_bytes": 1073741824,
  "used_bytes": 0
}

Response:
{"registered": true, "node_id": "node-6"}
```

## 5. 分片ID格式

```
{file_id}_{shard_index}
```

例如: `a1b2c3d4-e5f6-7890-abcd-ef1234567890_3`

## 6. 文件系统布局

每个节点的存储目录:
```
/data/shards/
  {file_id}/
    {file_id}_{0}.shard
    {file_id}_{3}.shard
```

文件名即shard_id + ".shard"后缀。
