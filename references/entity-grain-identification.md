# 实体粒度识别

**主查询设计前必查**。一条事件代表什么粒度（单实体/批量上报）—— 这决定了你是 `count(distinct pid)`、`countIf`、还是 `sum(length(splitByChar(',', list)))`。识别错了，主查询全盘错。

---

## 三个必答问题

写聚合 SQL 之前，先回答：

1. **事件实体粒度**：一条事件代表 1 个用户、1 个队伍/批次、1 局对局、还是 1 个匹配池？
2. **指标业务粒度**：业务问的是用户人次、队伍数、局数、还是匹配池数？
3. **两者是否一致**？不一致就要展开（`arrayJoin(splitByChar(',', list_field))`）或按列表长度加权（`sum(length(splitByChar(',', list_field)))`）。

**写成一句话**：「一条事件 = N 个 X，业务关心 M 个 X，所以分母是 sum(...) / count(...)」。

---

## 识别方法（10 秒搞定）

跑一行：

```sql
select * from events
  where `#event` = '<事件名>' and `#dt` = '<日期>'
  limit 1
```

看输出：

| 现象 | 说明 | 处理 |
|---|---|---|
| 主键字段（pid / uid）有数值 | **单实体事件** | `countIf` / `count(distinct pid)` 直接用 |
| 主键全 `0` 或 `null` + 有 list 字段（pid_list / players / batch_ids） | **批量上报**，每条事件一组实体 | 必须展开或按 list 长度加权 |

---

## List 字段类型陷阱

埋点平台常把"一组 ID"存成**逗号分隔的 String**，**不是 Array**。

| 类型 | 字段长得像 | 算成员数 | 展开成行 | 包含判断 |
|---|---|---|---|---|
| `String` | `"123,456,789"` | `length(splitByChar(',', X))` | `arrayJoin(splitByChar(',', X))` | `has(splitByChar(',', X), 'val')` |
| `Array` | `[123, 456, 789]` | `length(X)` | `arrayJoin(X)` | `has(X, 'val')` |

### 严重错误示例

- `length('123,456,789')` 算的是**字符数 11**，不是元素数 3 —— 用错口径会爆失真
- `position(pid_list, '12') > 0` 会把 `pid_list='1234,567'` 误匹配 → 必须用 `has(splitByChar(',', pid_list), '12')` 精确判断

---

## 真实案例：匹配体验查询双重踩坑

**事件**：`gameserver_match_process`（一次匹配过程会多条事件，stat 0/1/2/3 表示开始/跨区/取消/成功）。

### 第一次坑：聚合键唯一性

最初按 `match_id` group by 算成功率得 30%，业务直觉错。探查发现：单日 244 万事件只有 24K 个不同 `match_id`（约 100x 复用），不能按它聚合。

→ 改 `countIf(match_stat = X)` 重写。

### 第二次坑：实体粒度

改 `countIf` 后没识别到 `pid_list` 是批量上报。每条事件不是单玩家而是**一支队伍**（pid_list 是 String，逗号分隔，1~4 人组队）。**事件粒度成功率 37.80% ≠ 玩家粒度成功率 39.81%**，差 2.2 pp。

抽样校验抓出后才纠正：

```sql
-- 错的（事件粒度）：
countIf(match_stat = 0) as total
countIf(match_stat = 3) as success

-- 对的（玩家粒度）：
sum(if(match_stat = 0, length(splitByChar(',', pid_list)), 0)) as total
sum(if(match_stat = 3, length(splitByChar(',', pid_list)), 0)) as success
```

### 本可避免

写主查询前若先做实体粒度识别（`limit 3` 看一条记录是单玩家还是 pid_list 批量），10 秒能避免两次重写。**所以叫「必查」**。

---

## 检查清单

写主查询前，对照下面四条：

- [ ] 已跑 `limit 3` 看过一条原始事件长什么样
- [ ] 已识别主键字段是有效数值还是空（决定单实体 vs 批量）
- [ ] 已识别 list 字段类型是 String 还是 Array（决定用哪个函数）
- [ ] 已写下「一条事件 = N 个 X，业务关心 M 个 X」这句话

四条全勾才能动手写主查询。
