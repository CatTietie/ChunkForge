# ChunkForge 架构文档

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                       DOCKER COMPOSE NETWORK                         │
│                                                                       │
│  ┌───────────┐     ┌──────────────┐     ┌────────────────────────┐  │
│  │  Frontend  │     │  API Gateway │     │      Coordinator       │  │
│  │  React+D3  │◄───►│   FastAPI    │◄───►│   FastAPI + asyncio    │  │
│  │   :3000    │  WS │    :8000     │ HTTP│       :8001            │  │
│  └───────────┘     └──────┬───────┘     └────┬──────┬──────┬─────┘  │
│                           │                  │      │      │        │
│                           │            heartbeat  repair metadata    │
│                           │                  │      │      │        │
│                 ┌─────────┴──────┬───────┬──┴──────┴──────┴───┐    │
│                 │                │       │       │             │    │
│            ┌────┴───┐  ┌────────┴┐  ┌───┴────┐ ┌┴───────┐ ┌──┴──┐ │
│            │ Node-0 │  │ Node-1  │  │ Node-2 │ │ Node-3 │ │ ... │ │
│            │  :9000 │  │  :9000  │  │  :9000 │ │  :9000 │ │     │ │
│            └────────┘  └─────────┘  └────────┘ └────────┘ └─────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

## 组件详情

### Frontend (React + D3.js)
- **TopologyGraph**: D3 力导向图展示节点状态(绿/黄/红)和连接
- **ShardHeatmap**: 文件×节点矩阵，颜色区分数据/校验分片
- **EventLog**: WebSocket实时事件流
- **FileManager**: 上传/下载/删除操作
- **NodeControls**: 添加/移除/宕机/恢复节点

### API Gateway (FastAPI :8000)
- `POST /files/upload` — 接收文件 → RS encode → 分发分片
- `GET /files/{id}/download` — 收集分片 → RS decode → 返回原文件
- `POST /cluster/nodes/{id}/crash` — 标记宕机 → 触发修复
- `WS /ws/events` — 实时事件推送

### Coordinator (FastAPI :8001)
- 元数据存储(内存 + JSON持久化)
- 心跳监控(每2s检查超时)
- 修复状态机编排
- Term管理(脑裂防护)

### Storage Node (FastAPI :9000)
- 分片CRUD (PUT/GET/DELETE /shards/{id})
- 心跳上报(每1s → Coordinator)
- 文件系统存储: `/{file_id}/{shard_id}.shard`

## 数据流

### 上传流程
```
Client → Gateway: POST /files/upload (multipart)
Gateway: RS encode → 6 fragments
Gateway → Node-X: PUT /shards/{id} (×6, 并行)
Gateway → Coordinator: 写入元数据
Gateway → Frontend: WS event "file_uploaded"
```

### 下载流程
```
Client → Gateway: GET /files/{id}/download
Gateway → Coordinator: 查询分片位置
Gateway → Node-X: GET /shards/{id} (取任意4个)
Gateway: RS decode → 原始文件
Gateway → Client: 200 + 文件内容
```

### 故障修复流程
```
Coordinator: 心跳超时检测 / 手动crash
Coordinator: 识别受影响分片
Coordinator: 规划修复(选目标节点)
Coordinator → Nodes: GET 存活分片(k=4个)
Coordinator: RS reconstruct 缺失分片
Coordinator → Target: PUT 重建分片
Coordinator: 更新元数据
Coordinator → Frontend: WS events (progress)
```

## 纠删码参数
- **k=4**: 数据分片数量
- **m=2**: 校验分片数量
- **容错**: 最多丢失2个分片(或2个节点)仍可恢复
- **算法**: GF(2^8) Vandermonde矩阵 Reed-Solomon

## 脑裂防护: Term Fencing
1. Coordinator维护单调递增 term
2. 每次节点宕机 → term+1
3. 心跳响应携带 current_term
4. 节点复活时 → reconciliation协议
5. 清理已被修复的冗余分片
