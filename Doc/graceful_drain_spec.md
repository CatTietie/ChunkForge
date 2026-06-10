# 节点优雅排空与分片有序迁移需求规格

## 背景与目标
ChunkForge的NodeStatus定义了DRAINING状态，但从未被使用。当前下线节点的唯一方式是crash，触发紧急修复。紧急修复使用最少分片优先策略选择目标节点，不考虑目标节点的磁盘容量和负载，可能导致修复后分片集中在少数节点上。

需要实现节点优雅排空机制：运维标记节点进入排空状态后，系统有序地将该节点上的分片迁移到其他节点，迁移完成后再将节点标记为离线。迁移过程中节点仍可提供读服务。

## 需求清单
- R-DRAIN-01: 支持将节点标记为DRAINING状态，标记后节点不再接受新分片写入
- R-DRAIN-02: 排空过程将节点上的全部分片迁移到其他在线节点
- R-DRAIN-03: 迁移目标选择必须考虑目标节点剩余容量和当前分片数
- R-DRAIN-04: 排空期间节点仍可响应读请求，保证数据可用性
- R-DRAIN-05: 排空期间节点心跳正常上报，Coordinator不将其标记为宕机
- R-DRAIN-06: 排空完成后自动将节点状态转为OFFLINE，清理元数据
- R-DRAIN-07: 排空过程中节点意外宕机时，未迁移的分片按紧急修复流程处理
- R-DRAIN-08: 支持取消排空操作，已迁移的分片保留在新节点，不再迁回
- R-DRAIN-09: 通过WebSocket推送排空进度事件
- R-DRAIN-10: 前端显示排空进度和预计剩余时间

## 现有架构约束
- NodeStatus.DRAINING已定义但未使用，节点路由和心跳逻辑需适配
- 修复引擎的on_node_failed与排空迁移逻辑不同：修复是紧急重建，排空是有序迁移
- 分片写入路由（upload流程）需排除DRAINING节点
- 心跳监控需跳过DRAINING状态的超时检查

## 技术栈约束
- 后端：Python FastAPI + asyncio
- 节点存储：本地文件系统
- 通信：httpx AsyncClient
- 前端：React + D3.js

## 数据模型变更
- 新增 DrainTask 模型：task_id, node_id, total_shards, migrated_shards, state
- 新增 DrainState 枚举：PENDING / MIGRATING / VERIFYING / COMPLETED / CANCELLED / INTERRUPTED
- 新增 EventType：DRAIN_STARTED / DRAIN_PROGRESS / DRAIN_COMPLETED / DRAIN_CANCELLED
- NodeInfo 扩展：drain_task_id (Optional[str])

## 引擎流程设计
1. 标记DRAINING → 创建DrainTask → 排除该节点的新分片写入
2. 逐分片迁移：读取源分片 → 选择容量充足的目标节点 → 写入 → 验证 → 更新元数据 → 删除源分片
3. 全部分片迁移完成 → 节点状态转OFFLINE → 发布事件
4. 中途取消 → 已迁移分片保留 → 节点恢复ONLINE → 节点上剩余分片不变

## 边界条件与异常处理
- 排空期间新文件上传：DRAINING节点不参与分片分配
- 排空期间修复引擎触发：排空暂停让路给修复，修复完成后恢复排空
- 目标节点在迁移过程中宕机：重选目标
- 集群在线节点不足以接收排空分片：排空暂停等待新节点加入
- 排空期间同一文件的其他分片所在节点也宕机：优先处理紧急修复

## 验收标准
- 标记节点排空后，该节点不再接收新分片，已有分片有序迁移到其他节点
- 迁移期间文件可正常下载
- 迁移完成后节点状态为OFFLINE，所有分片不在该节点上
- 节点意外宕机时未迁移分片走紧急修复
- 前端实时显示排空进度
