# 数据探查模板集

写主查询前用样本验证假设。**几行探查 SQL 比主查询出错回头查便宜得多**。

## 触发场景（任一命中就探查）

- 准备按某 ID `group by`（match_id、order_id、session_id…）→ 验唯一性
- 不确定字段枚举值范围 → 看分布
- 字段名相似但含义模糊（value vs after、create_time vs login_time）→ 取单条记录看
- 业务逻辑复杂（一次行为对应多条事件）→ 抽 1~3 个用户完整事件流
- 对量级没把握 → 先 count 单日

---

## 模板 0：实体粒度识别（**最关键，写主查询前必跑**）

```sql
select * from events
  where `#event` = '<事件名>' and `#dt` = '<日期>'
  limit 3
```

**重点看**：
- 主键字段（pid / uid / user_id）是否有值？
- 有没有 list 类字段（pid_list / players / batch_ids…）？
- list 字段类型是 `String`（含逗号字符串）还是 `Array`？

详见 [entity-grain-identification.md](entity-grain-identification.md)。

---

## 模板 1：聚合键唯一性

```sql
select count(*) as total_events,
        count(distinct <候选键>) as distinct_keys,
        count(distinct (<候选键>, <辅助列>)) as distinct_with_aux
  from events
  where `#event` = '<事件名>'
    and `#dt` = '<日期>'
```

**判定**：
- `total_events / distinct_keys ≈ 1` → 候选键唯一，可以直接 group by
- 比例 > 1 → 候选键不唯一（被复用），需要加辅助列才唯一，或换聚合方法

**真实案例**：`gameserver_match_process` 单日 244 万事件只有 24K 不同 `match_id`（约 100x 复用），按 match_id group by 算成功率会失真到 30%。

---

## 模板 2：枚举值分布

```sql
select <字段>, count(*) as cnt
  from events
  where `#event` = '<事件名>'
    and `#dt` = '<日期>'
  group by 1
  order by 2 desc
```

适用：`status`、`stat`、`login_type`、`source` 这种有限枚举的字段，确认所有可能取值再写 `case when` / `countIf`。

---

## 模板 3：单条记录展开（看字段实际长什么样）

```sql
select *
  from events
  where `#event` = '<事件名>'
    and `#dt` = '<日期>'
  limit 5
```

适用：字段名相似但含义模糊（value vs after）、不知道字段是数值还是字符串、不知道时间戳是秒还是毫秒。

---

## 模板 4：用户样本完整事件流

```sql
select `#time`, <关键字段们>
  from events
  where `#event` = '<事件名>'
    and `#dt` = '<日期>'
    and pid in (<挑 1~3 个 pid>)                     -- 单实体事件
    -- 或: and has(splitByChar(',', pid_list), '<pid>')  -- 批量上报事件
  order by pid, `#time`
```

适用：业务逻辑复杂（一次行为对应多条事件，如匹配/支付有多个状态流转），抽真实样本看完整流转规律。

---

## 文件归档约定

- 探查 SQL 写到 `queries/<场景>/probe_<内容>.sql`
- 探查结果落到 `outputs/<场景>/probe_<内容>.csv`
- **跟主查询同子目录归档**，保留决策链路，**不要跑完即删**

例：

```
queries/match_experience/
  probe_event_grain.sql       # 看一条事件几个 pid
  probe_match_id_unique.sql   # match_id 唯一性
  probe_stat_distribution.sql # match_stat 枚举分布
  main.sql                    # 最终主查询

outputs/match_experience/
  probe_event_grain.csv
  probe_match_id_unique.csv
  probe_stat_distribution.csv
  main_2026-04-14_2026-04-20.csv
```

后续看到这个目录的人，能从探查 → 主查询的演进过程理解为什么主查询是这么写的。
