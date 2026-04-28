---
name: ds
description: |
  数据取数工程师 skill。接收数据需求，优先用 FunnyDB 看板取数；看板覆盖不到时
  自主写 ClickHouse SQL，通过 FunnyDB analyse/query 直接执行，结果落 UTF-8 BOM
  CSV 后交付（SQL + CSV 路径 + 预览 + 抽样校验摘要）。不做分析、不画图、不下结论。
  触发：用户使用 `/取数` 命令，或表达「取数」「写 SQL」「查数据」「跑个数」等意图。
---

# DS：数据取数 skill（看板优先 + 自主 SQL 兜底）

把任意数据需求转成可交付的 CSV 文件：先在 FunnyDB 看板里找现成的，找不到就自己写 SQL 直接跑。

## 触发条件

- 用户使用 `/取数` 命令
- 用户表达「取数」「写 SQL」「查数据」「跑个数」「拉一下 X 数据」等意图

---

## 边界

- **要做**：拆需求 → 找看板/写 SQL → 执行 → 结果落 CSV → 交付（SQL + CSV 路径 + 预览 + 校验摘要）
- **不做**：解读数据、画图、下结论、写分析报告 —— 那些是 DA agent / 分析师的活

---

## 前置依赖

1. **Python ≥ 3.8**（执行 `scripts/run_sql.py`）
2. **funnydb skill** 已安装且授权可用：
   - 仓库：`https://git.sofunny.io/data-analysis/funnydb-skills.git`
   - Linux/macOS 直接运行；Windows 通过 WSL 桥接（详见 README）
3. **app_id**：使用前必须确认要查哪个 FunnyDB app（不要猜，不知道就问用户）

---

## 完整执行流程

```
Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 6 → Step 7 → Step 8
拆需求   找看板   元数据探查   写 SQL   执行    抽样校验  落 CSV   交付
         (优先)
```

### Step 1：需求拆解（四要素）

把模糊需求拆成可执行的四要素，**任一不清晰必须二次询问，禁止猜**：

| 要素 | 要确认到的颗粒度 | 反例 |
|---|---|---|
| **核心指标** | 具体指标名 + 算法（如 DAU = `count(distinct pid)`，留存 = `次日活跃 / 当日活跃`） | 「用户活跃情况」 |
| **维度粒度** | 按哪些字段 group by（日期、模式、渠道、等级…） | 「分组看下」 |
| **时间范围** | **绝对日期**（如 2026-04-14 ~ 2026-04-20） | 「近 7 天」「上个月」 |
| **过滤条件** | 排除规则（AI、异常时长…）+ 包含规则（特定模式、客户端…） | 「正常用户」 |

> 「近 7 天」「上周」必须换算成绝对日期再开干 —— 取数日 + 7 天的窗口很容易和分析期错位。

### Step 2：先找看板（FunnyDB dashboards）

**禁止凭记忆/历史快照硬编码 panel_id**。每次新需求都按下面四步走：

```bash
cd <funnydb skill 路径>   # 通常是 .claude/skills/funnydb 或 ~/.claude/skills/funnydb

# (1) 拉完整看板目录（dashboard_spaces 分组 + 嵌套 dashboards）
bash scripts/funnydb post /api/v1/open/skillhub/tools/dashboards/search \
  --data '{"app_id": <APP_ID>}'

# (2) 按业务关键词从返回值的 spaces.name + dashboards.name + description 里筛候选

# (3) 选定 dashboard 后查 panel 清单
bash scripts/funnydb post /api/v1/open/skillhub/tools/dashboards/details \
  --data '{"app_id": <APP_ID>, "dashboard_id": <DASHBOARD_ID>}'

# (4) 选定 panel 后查变量+口径，再拉数据
bash scripts/funnydb post /api/v1/open/skillhub/tools/panels/details \
  --data '{"app_id": <APP_ID>, "panel_id": <PANEL_ID>}'

bash scripts/funnydb post /api/v1/open/skillhub/tools/panels/data \
  --data '{"app_id": <APP_ID>, "panel_id": <PANEL_ID>, "args": {...}}'
```

**看板满足的判定标准**（同时满足才算「满足」）：
- ✅ 看板的指标定义和需求一致（不只是名字像）
- ✅ 看板支持的维度切分覆盖需求维度
- ✅ 看板的过滤条件能精确表达需求过滤
- ✅ 看板的时间范围能覆盖需求时间窗口

满足 → 拉数据进 Step 7（落 CSV 交付）；不满足 → 进 Step 3 走自主 SQL 路径。

> **不要硬塞相似看板**。看板口径与需求差太多还硬用，结果会被分析师甩回来重做。

### Step 3：元数据查询（业务含义 + 字段校验）

走自主 SQL 路径前，先用 FunnyDB analyse 接口拿元数据。**禁止凭经验猜事件名/字段名**。

#### (a) 业务含义 — event 模型接口

含 `description`（业务说明，~70% 字段覆盖）、`meta_type`（preset/custom/virtual）、`has_history_versions`：

```bash
# 事件清单（含中文 title）
bash scripts/funnydb post /api/v1/open/skillhub/tools/analyse/events \
  --data '{"app_id": <APP_ID>}'

# 某事件全部属性（含 description）
bash scripts/funnydb post /api/v1/open/skillhub/tools/analyse/properties \
  --data '{"app_id": <APP_ID>, "event_name": "<事件名>"}'
```

#### (b) raw_sql 字面量确认 — raw_sql 模型接口

仅当需要确认 SQL 写法（低基数文本字段、表 schema 字段类型）时：

```bash
# SQL 写法用的事件清单（多 name_for_sql 字面量）
bash scripts/funnydb post /api/v1/open/skillhub/tools/analyse/sql/events \
  --data '{"app_id": <APP_ID>}'

# 事件属性（SQL 字面量）
bash scripts/funnydb post /api/v1/open/skillhub/tools/analyse/sql/event-properties \
  --data '{"app_id": <APP_ID>, "event_name": "<事件名>"}'

# 表 schema
bash scripts/funnydb post /api/v1/open/skillhub/tools/analyse/sql/columns \
  --data '{"app_id": <APP_ID>, "name": "events"}'
```

> 顺序：先 (a) 看业务含义，后 (b) 校 SQL 字面量。两边对得上再动手写 SQL。

### Step 4：数据探查（**别跳！**）

**有了直接执行能力后，假设要先用样本验证再写主查询。** 凭埋点文档+经验拍脑袋的聚合键、字段含义、过滤条件常和线上对不上 —— 与其等主查询出错回头查，不如先花几行 SQL 实测。

#### 触发场景（任一命中就探查）

- 准备按某 ID `group by`（match_id、order_id、session_id…）→ 验唯一性
- 不确定字段枚举值范围 → 看分布
- 字段名相似但含义模糊（value vs after、create_time vs login_time）→ 取单条记录看
- 业务逻辑复杂（一次行为对应多条事件）→ 抽 1~3 个用户完整事件流
- 对数据量级没把握 → 先 count 单日

#### 实体粒度识别（**必查！**）

主查询设计前先回答三件事：
1. **事件实体粒度**：一条事件代表 1 个用户、1 个队伍/批次、1 局对局、还是 1 个匹配池？
2. **指标业务粒度**：业务问的是用户人次、队伍数、局数、还是匹配池数？
3. **两者是否一致**？不一致就要展开（`arrayJoin(splitByChar(',', list_field))` 或按列表长度加权）。

**识别方法**（`limit 1` 看一条原始记录就够）：
- 主键字段是数值 → 单实体事件，`countIf` / `count(distinct pk)` 直接用
- 主键全 0/null + 有 list 类字段（pid_list / players / batch_ids…）→ 批量上报，每条事件代表一组实体，得展开或加权
- 字段类型 `String` 含逗号 → `length(splitByChar(',', X))` 算成员数；`Array` 类型才能直接 `length(X)` `arrayJoin(X)`

**写主查询前必须落到一句话**："一条事件 = N 个 X，业务关心 M 个 X，所以分母是 sum(...) / count(...)"。

#### 探查模板

```sql
-- 模板0：实体粒度识别（最关键，写主查询前必跑）
select * from events
  where `#event` = '<事件名>' and `#dt` = '<日期>'
  limit 3
-- 看主键是否有值 / 有没有 list 字段 / 类型是 String 还是 Array

-- 模板1：聚合键唯一性
select count(*) as total_events,
        count(distinct <候选键>) as distinct_keys,
        count(distinct (<候选键>, <辅助列>)) as distinct_with_aux
  from events
  where `#event` = '<事件名>' and `#dt` = '<日期>'

-- 模板2：枚举值分布
select <字段>, count(*) as cnt
  from events
  where `#event` = '<事件名>' and `#dt` = '<日期>'
  group by 1 order by 2 desc

-- 模板3：单条记录展开（看字段实际长什么样）
select * from events
  where `#event` = '<事件名>' and `#dt` = '<日期>'
  limit 5

-- 模板4：用户样本完整事件流
select `#time`, <关键字段们>
  from events
  where `#event` = '<事件名>'
    and `#dt` = '<日期>'
    and pid in (<挑 1~3 个 pid>)                   -- 单实体事件
    -- 或: and has(splitByChar(',', pid_list), '<pid>')  -- 批量上报事件
  order by pid, `#time`
```

> 探查文件命名 `probe_<内容>.sql`，与主查询同子目录归档（保留决策链路，不要跑完就删）。

### Step 5：编写静态日期 SQL

按 [references/clickhouse-sql-conventions.md](references/clickhouse-sql-conventions.md) 写。核心规则：

- **日期统一静态值**：`` `#dt` between '2026-04-14' and '2026-04-20' ``，**禁用** `${dt:date}` 等平台模板占位符
- **每个子查询都要带 `#dt` 过滤** —— 不带就全表扫描
- `#dt` / `#event` / `#time` 等系统字段用**反引号**
- `group by` / `order by` 用数字序号
- 关键字全小写
- 子表连接默认 `left join`
- **JOIN ON 只写等值条件** —— ClickHouse 不支持 `>=` / `between` 等不等式 JOIN
- **不做展示格式化** —— 不乘 100、不 round、不强制小数位（交给下游分析师）
- **中文别名用双引号**：`as "日活跃用户数"`
- ClickHouse 标量值用子查询，不用 cross join；CTE 保持独立不串成链
- 多次状态场景取最新值用 `argMax`，别 `row_number`
- 优先 ClickHouse 原生函数：`argMin`/`argMax`/`uniqExact`/`countIf`

### Step 6：执行 SQL

**统一走 `scripts/run_sql.py`** —— SQL 写到 `.sql` 文件再调用，**不要在 bash 里 inline 含反引号的 SQL**。funnydb shim 经过 WSL `bash -c` 会把 `` `#dt` `` 这类反引号当命令替换吃掉；脚本已自动转义为 `\u0060`。

#### 目录约定（每个需求一个独立子文件夹）

```
queries/<场景>/
  main.sql                # 最终交付的主查询
  probe_<内容>.sql        # 探查脚本（实体粒度/唯一性/枚举…）
  verify_<内容>.sql       # 抽样校验脚本

outputs/<场景>/
  main_<起>_<止>.csv      # 主查询结果
  probe_<内容>.csv        # 探查结果
  verify_<内容>.csv       # 校验结果
```

子目录名 = 场景 snake_case（如 `match_experience`、`user_retention_v62`）。**所有探查/校验文件随主查询一起归档**，保留完整决策链路，不要跑完即删。

#### 调用方式

```bash
# 假设 ds-skill 装在 .claude/skills/ds，funnydb 装在 .claude/skills/funnydb
PYTHONIOENCODING=utf-8 python -X utf8 \
  .claude/skills/ds/scripts/run_sql.py \
  --app-id <APP_ID> \
  --funnydb-dir <funnydb skill 路径> \
  --file queries/<场景>/main.sql \
  --out outputs/<场景>/main_<起>_<止>.csv
```

脚本输出：`total_count` + 写入路径 + 前 10 行 Markdown 预览。

#### 结果验证

- `total_count` 与 `rows` 长度对得上预期再交付
- 报错 → 读 message 修 SQL，**不要重试相同语句**
- 0 行 → 单独跑事件计数确认事件名+日期是否对
- 行数远超预期 → 警惕维度爆炸或漏了过滤
- 大查询前先小日期范围（1~2 天）跑一次验证

### Step 7：抽样校验（**别跳！**）

**主查询跑完后，从结果里挑样本回原始事件做反向验证**。聚合 SQL 写对≠语义对 —— 漏 NULL、双计某种 stat、跨天事件并到一天 —— 抽样比对原始记录是发现这类错误的最便宜手段。

#### 触发场景（任一命中就抽）

- 主查询出了任何指标（成功率、消耗、时长、留存…）
- 数值看着「差不多对」但没有 ground truth
- 涉及多 stat / 多事件 union / argMax 这类容易绕错的逻辑

#### 抽样原则

- **挑代表性样本，不是随机** —— 一个高活跃 + 一个中等 + 一个边界（指标极值所在的维度）
- **数量少而精** —— 1~3 个 pid 足够
- **手算可复现** —— 抽出来的原始事件，用 Excel/口算就能复现主查询的聚合数

#### 校验模板

```sql
-- 模板1：用户样本完整事件流（最常用）
select `#time`, <关键字段>
  from events
  where `#event` = '<事件名>'
    and `#dt` = '<日期>'
    and pid = <从主查询挑出的 pid>
  order by `#time`
-- 人工核对：该 pid 的指标按口径手算 = 主查询那一行

-- 模板2：维度切片精确回查
select countIf(<条件 A>) as a,
        countIf(<条件 B>) as b
  from events
  where `#event` = '<事件名>'
    and `#dt` = '<日期>'
    and <主查询的 group 维度精确还原>
-- 期望：与主查询那一行严格相等

-- 模板3：极值样本（看异常上限是否真合理）
select pid, <相关字段>
  from events
  where `#event` = '<事件名>'
    and `#dt` = '<日期>'
    and <极值发生的维度>
  order by <极值字段> desc
  limit 5
```

#### 通过标准

- ≥1 个用户样本：原始事件按口径手算 = 主查询数值
- ≥1 个维度切片：精确条件回查 = 主查询那一行
- 极值样本看着合理（不是脏数据撑起来的均值/最大值）

#### 不通过怎么办

- 数值偏差 → 查 `countIf` 条件、`group by` 维度、`#dt` 过滤是否漏
- 极值脏 → 主查询加范围过滤后重跑（如 `wait_sec between 0 and 600`）
- **不要直接交付「差不多」的结果**

### Step 8：落 CSV + 交付

CSV 路径：`outputs/<场景>/main_<开始日期>_<结束日期>.csv`

- **必须 UTF-8 BOM**（`\xEF\xBB\xBF`），否则 Windows 中文乱码 —— `run_sql.py` 写 CSV 时用 `utf-8-sig` 已自动加
- 表头用查询返回的 `columns`，行用 `rows`
- 不在 CSV 里做格式化（不乘 100、不 round），原样落

#### 交付三件套 + 校验摘要

回给用户：
1. **SQL 代码块** —— 完整可复用的静态日期 SQL（指向 `queries/<场景>/main.sql`）
2. **CSV 文件路径** —— 相对路径
3. **前 5~10 行预览** —— Markdown 表格
4. **抽样校验摘要**（一两句话）—— 抽了哪个 pid / 哪个维度切片，原始事件数 vs 聚合数对得上

不写分析、不下结论。

---

## SQL 铁律

1. **先查埋点+元数据再写** —— 不凭经验
2. **聚合键先验证唯一性** —— 看似唯一的 ID（如 match_id）可能跨用户/跨过程重复，假设错就全盘错
3. **搞清字段含义** —— `value`（变化值）vs `after`（剩余量）这种容易混；模糊就 `limit 5` 看实际数据
4. **跑完必抽样校验** —— 主查询的聚合值，至少抽 1 个用户样本 + 1 个维度切片回原始事件比对
5. **精简字段** —— 用不到的不取
6. **多次状态场景** —— 取存量用 `argMax`，不要 `row_number`
7. **优先 ClickHouse 原生函数** —— `argMin`/`argMax`/`uniqExact`
8. **时区/单位意识** —— `#time` 毫秒 0 时区，`#dt` 已转东八区，业务时间字段单位需查 schema

---

## 常见踩坑速查

| 问题 | 解决 |
|---|---|
| funnydb shim 在 bash 里 inline SQL 反引号被吃掉 | 必须 `--file` 传 `.sql` 文件，不要 `--sql` inline |
| Windows 调 funnydb 走 WSL bash 报路径错 | 设 `GIT_BASH` 环境变量指向 Git Bash 真实路径 |
| ClickHouse JOIN 报错 | 检查是否在 `on` 子句里写了 `>=` / `between`，必须只写等值条件 |
| 0 行 | 先单独跑 count 确认事件名 + 日期范围 |
| 行数巨多 | 检查 join 是否漏等值条件、group by 是否漏维度 |
| 中文 CSV Windows 乱码 | 必须 UTF-8 BOM，run_sql.py 已自动 |
| 看似唯一的 ID 不唯一 | `count(*) vs count(distinct id)` 探查，差距大就别按它聚合 |
| List 字段 `length(X)` 算字符数 | String 类型用 `length(splitByChar(',', X))`；Array 类型才能直接 `length(X)` |

---

## 看板 vs SQL 决策树速查

```
拿到需求
  │
  ├─ Step 1：拆四要素（指标/维度/时间/过滤），不清晰回问
  │
  ├─ Step 2：dashboards/search 拉看板目录，按业务关键词找候选
  │   │
  │   ├─ 有看板 + 口径精确匹配（指标/维度/过滤/时间窗口都覆盖）
  │   │   └→ panels/data 拉数据 → Step 8 落 CSV
  │   │
  │   └─ 没看板 / 口径不匹配 → 进 Step 3
  │
  ├─ Step 3：analyse/events + analyse/properties 查埋点元数据
  ├─ Step 4：实体粒度识别 + 探查模板验证假设
  ├─ Step 5：写静态日期 SQL（按 references/clickhouse-sql-conventions.md）
  ├─ Step 6：run_sql.py 执行
  ├─ Step 7：抽样校验
  └─ Step 8：落 CSV + 交付（SQL + 路径 + 预览 + 校验摘要）
```

---

## 关键文件

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 本文档（工作流入口） |
| `scripts/run_sql.py` | FunnyDB analyse/query 执行器 + CSV 落盘 |
| `references/clickhouse-sql-conventions.md` | SQL 书写规范（缩进、命名、铁律） |
| `references/data-probing-templates.md` | 探查 SQL 模板集（实体粒度/唯一性/枚举/样本流） |
| `references/result-verification.md` | 抽样校验方法论 + 模板 |
| `references/entity-grain-identification.md` | 单实体 vs 批量上报识别方法 |
| `examples/sample-query/` | 示例查询目录结构 |
