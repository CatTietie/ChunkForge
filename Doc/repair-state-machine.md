# 修复状态机规范

## 状态图

```
                    ┌──────────┐
                    │  HEALTHY │
                    └────┬─────┘
                         │
          heartbeat_timeout / manual_crash
                         │
                         ▼
                    ┌──────────────┐
                    │DETECTING_LOSS│
                    └────┬─────────┘
                         │
               shards_identified
                         │
                         ▼
                    ┌───────────────┐
                    │PLANNING_REPAIR│
                    └───┬───────┬───┘
                        │       │
          plan_ready    │       │  insufficient_shards (< k survive)
                        │       │
                        ▼       ▼
           ┌────────────────┐  ┌──────────────┐
           │ RECONSTRUCTING │  │DEGRADED_FATAL│
           └───────┬────────┘  └──────────────┘
                   │
        all shards reconstructed
                   │
                   ▼
           ┌───────────┐
           │  VERIFYING │
           └───┬────┬───┘
               │    │
     checksum  │    │  mismatch
       pass    │    │
               ▼    ▼
      ┌──────────┐ ┌───────────┐
      │COMPLETED │ │RETRY(≤3次)│──→ DEGRADED_FATAL
      └──────────┘ └───────────┘
```

## 状态说明

| 状态 | 入口动作 | 退出条件 |
|------|----------|----------|
| HEALTHY | 正常运行 | 心跳超时(3次丢失=3s) 或 手动crash |
| DETECTING_LOSS | 查询元数据，列出宕机节点上的所有(file_id, shard_index)对 | 分片列表完成 |
| PLANNING_REPAIR | 对每个文件: 验证≥k个分片存活; 选目标节点(最少分片优先); 入队修复任务 | 所有任务已规划 或 分片不足 |
| RECONSTRUCTING | 并发fetch k个存活分片; RS reconstruct缺失分片; 写入目标节点 | 所有分片已写入 |
| VERIFYING | 读回新写入分片，计算checksum，与元数据比对 | 所有校验通过 |
| COMPLETED | 更新元数据(新分片位置); 发布事件; 文件标记healthy | 返回HEALTHY |
| DEGRADED_FATAL | 发布告警; 文件标记lost | 等待人工介入 |

## 并发模型

- 多文件修复并行执行(asyncio.gather)
- 同一文件内，分片获取使用asyncio信号量限流
- 默认最大并发=4(通过REPAIR_CONCURRENCY环境变量配置)

## 错误处理

- 分片获取失败: 尝试其他存活节点上的同index分片(如果有冗余)
- 写入目标失败: 选择另一个目标节点重试
- 最多重试3次后标记DEGRADED_FATAL
- 每次重试递增retry_count

## Term Fencing 交互

修复开始时 term 已递增。如果修复期间原节点恢复:
1. 原节点心跳到达时检测到 stale term
2. Coordinator下发 `inventory_report` 命令
3. 对比元数据 → 清理冗余分片
4. 不影响正在进行的修复任务
