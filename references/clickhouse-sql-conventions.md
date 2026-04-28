# ClickHouse SQL 书写规范

DS skill 写出的 SQL 走 FunnyDB `analyse/query` (model=raw_sql) 跑在 ClickHouse 上。下面是必须遵守的格式与铁律。

## 格式示例

```sql
select `#dt`,
        count(distinct pid) as dau
  from events
  where `#event` = 'gameserver_login'
    and `#dt` between '2026-04-14' and '2026-04-20'
    and login_type = 0
  group by 1
  order by 1
```

## 缩进规则

- `select` 顶格，首字段同行；后续字段对齐（**8 空格**）
- `from` / `where` / `group by` / `order by` 缩进 **2 格**
- `and` / `or` 缩进 **4 格**
- 子查询保持同样的层级关系
- 关键字**全小写**

## 必须遵守的规则

### 日期与系统字段

- **日期统一用静态值**：`` `#dt` between '2026-04-14' and '2026-04-20' ``
- **禁用** `${dt:date}`、`{date}` 等平台模板占位符 —— DS 走直接执行通道
- `#dt` / `#event` / `#time` 等以 `#` 开头的系统字段必须用**反引号**
- `#dt` 已转东八区，可直接用作分区过滤
- `#time` 是毫秒时间戳，**0 时区**，需要本地时间时手动 `+ 28800000`
- 业务时间字段单位查 schema（`create_time` / `last_offline_time` 等通常是秒）

### 分组与排序

- `group by` / `order by` 用**数字序号**（`group by 1, 2`）
- 子查询里也保持序号，避免改字段名时漏改

### JOIN 规则

- 子表连接默认 `left join`
- **JOIN ON 只写等值条件** —— ClickHouse **不支持** `>=` / `between` / `like` 等不等式 JOIN
- 不等式条件移到 `where` 子句
- ClickHouse **标量值用子查询**，不用 cross join；CTE 保持独立不串成链

### 字段精简与展示

- **不做展示格式化** —— 不乘 100、不 round、不强制小数位（这是分析师的活）
- 用不到的字段不取
- **中文别名用双引号**：`as "日活跃用户数"`

### 性能

- **每个子查询都要带 `#dt` 过滤** —— 不带就全表扫描，会被风控砍
- 大查询前先用小日期范围（1~2 天）跑一次验证
- 优先 ClickHouse 原生函数：`argMin` / `argMax` / `uniqExact` / `countIf` / `sumIf` / `groupArray`

### 多次状态/取最新值

- 取「最后一次的存量」用 `argMax(value, time)`
- **不要用 `row_number()`** —— ClickHouse 窗口函数性能差且语义易错

### 分布式查询

- 跨分片 `IN` 查询用 `global in`（不是 `in`），否则会广播子查询到每个分片导致超时
- 例：`pid global in (select pid from ... where ...)`

---

## SQL 铁律（按重要性排序）

1. **先查埋点+元数据再写** —— 不凭经验，用 `analyse/properties` / `analyse/sql/event-properties` 拿字段定义
2. **聚合键先验证唯一性** —— 看似唯一的 ID（如 match_id、order_id）可能跨用户/跨过程重复；**不确定就先跑探查 SQL 实测**
3. **搞清字段含义** —— `value`（变化值）vs `after`（剩余量）这种容易混；模糊就 `limit 5` 看真实数据
4. **跑完必抽样校验** —— 主查询的聚合值，至少抽 1 个用户样本 + 1 个维度切片回原始事件比对
5. **精简字段** —— 用不到的不取
6. **多次状态场景** —— 取存量用 `argMax`，不用 `row_number`
7. **优先 ClickHouse 原生函数** —— `argMin`/`argMax`/`uniqExact`
8. **时区/单位意识** —— `#time` 毫秒 0 时区，`#dt` 东八区
9. **写完先小范围跑验证**，再扩到完整时间段

---

## 失败处理

- **SQL 报错** → 读错误，定位语法/字段问题，**改了再跑，不要重试相同 SQL**
- **0 行** → 单独跑事件计数，先确认事件名+日期对不对
- **行数巨多** → 检查 join 是否漏等值条件、group by 是否漏维度
- **执行超时** → 缩小日期范围或加更精确的 `#dt` 过滤
- **元数据查不到事件名** → 停下来，**不要在 SQL 里猜事件字面量**
