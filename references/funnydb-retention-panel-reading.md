# FunnyDB 留存面板（event_model=retention）数据解析规则

调 `panels/data` 拿到 `event_model=retention` 类面板的返回 JSON 时，按本文档读 —— **不要凭直觉数下标**，FD 解析层对 `values` 数组用了"基数 + 留存"的混合排布，少数一位就会偏 1 天，撞到不同星期几的活跃数可能差 1~2 pp。

## 数据结构

返回 JSON 的关键字段：

| 字段 | 含义 |
|---|---|
| `key_dates` | 留存日偏移数组，如 `[0, 1, 2, ..., 30]` |
| `x` | cohort 起始日期数组，每个对应一行 |
| `y` | map：cohort 日期 → group 对象数组 |
| `stage_avg` | 跨所有 cohort 的阶段平均（单元素数组） |
| `z` | 阶段事件 title 数组：`[起始事件, 回访事件]` |

每个 group 对象（在 `y[date][i]` 或 `stage_avg[0]` 下）含：

| 字段 | 含义 |
|---|---|
| `values` | 留存绝对值数组，**长度 = key_dates 长度 + 1** |
| `lost_values` | 流失绝对值数组，与 `values` 同长 |
| `values_percent` | 留存率数组，**仅 stage_avg 提供**，单日 cohort 没有 |
| `lost_values_percent` | 流失率数组，与 values_percent 配套 |
| `invalid_index` | 从该下标起数据不可信（窗口未闭合） |
| `last_valid_date_indexes` | 各位置参与平均的有效 cohort 数（仅 stage_avg） |

## values 数组对齐（核心）

`values` 比 `key_dates` 多 1 个元素，对齐方式：

| values 下标 | 含义 |
|---|---|
| `values[0]` | **cohort 基数**（不对应任何 key_date，**不是留存值**） |
| `values[i+1]` | `key_dates[i]` = Day i 的留存绝对值 |

举例 `key_dates = [0, 1, 2, ..., 7]`：

| 位置 | key_date | 含义 |
|---|---|---|
| `values[0]` | — | cohort 基数 |
| `values[1]` | Day 0 | 同日返回（通常 = 基数 = 100%） |
| `values[2]` | Day 1 | 次日返回（业内"次留"） |
| `values[3]` | Day 2 | Day 2 返回 |
| `values[7]` | Day 6 | Day 6 返回（业内"7留"，因当天算第 1 天，第 7 天 = Day 6） |
| `values[14]` | Day 13 | Day 13 返回（业内"14留"） |
| `values[N]` | Day N-1 | 业内"N留"绝对值 |

> **业内通用 SQL 留存口径速查**（基于"注册当天算第 1 天"的传统口径）：
>
> - `次留 = values[2]`
> - `3留 = values[3]`
> - `7留 = values[7]`
> - `14留 = values[14]`
> - `30留 = values[30]`
> - **`N留 = values[N]`**（N ≥ 1）
> - **N留率 = `values[N] / values[0]`**

各业务团队对"N留"的口径定义可能略有差异（注册当天算第 0 天还是第 1 天），落地前先和分析师对一次：**业务说的"N留"是不是 init_date + (N-1) 天还活跃**。

## 阶段平均（多 cohort 汇总）

`stage_avg.values_percent[N]` 是 FD 已经按各 cohort 各自留存率加权平均后的 N 留率，**直接用，不要手算** `stage_avg.values[N] / stage_avg.values[0]`：

- `stage_avg.values` 是各 cohort 人数累加，**越靠后的 cohort 越多 null（窗口未闭合）**，分子被拖低
- 直接相除会得到偏低的"留存率"，不是真实平均

正确读法：**N留率 = `stage_avg.values_percent[N]`**

## 单日 cohort

`y[date][0]` 没有 `values_percent` 字段，必须自己 `values[N] / values[0]` 算。单日 cohort 受周末/节假日效应大（cohort 落在周一时 7留 撞周日高峰会偏高），单点波动不要直接读，对比口径优先用 `stage_avg` 或自己拉窗口均值。

## null vs 0

- `null`：窗口未闭合（cohort_date + N 还在未来），数据未来才有
- `0`：窗口已闭合，确实无人留存

呈现给业务时不要把两者混作一谈 —— `null` 标"数据未闭合"，`0` 是真实留存为零。

## invalid_index

从该下标起的数据不完整或不可信。一般 `values[invalid_index .. ]` 是 `null` 或正在累积，呈现表格时可以截断或标灰。

## 留存衰减

业内常用衰减公式：

> **N留衰减 = N留率 / 次留率**

衡量从次日到第 N 天的粘性保持能力。比率越接近 1 衰减越慢；越低衰减越快。

注意：**单日 cohort 的衰减比率可能 >1**（比如周一 cohort 的次留落周二低谷、7留 落周日高峰，分母被低估、分子被高估）。比较留存衰减时应取多 cohort 均值（一周或更长窗口）平掉星期效应，不要拿单日比率下结论。

## 排查清单（数对不上时按这个查）

1. **是不是把 `values[0]` 当成留存值用了？** —— `values[0]` 是基数
2. **是不是直接除了 `stage_avg.values[N]/values[0]`？** —— 应该直接读 `values_percent[N]`
3. **是不是手数下标错了一位？** —— 默念"基数=values[0]，次留=values[2]，N留=values[N]"
4. **是不是混淆了"业内 N留"和"FD UI 第N日"？** —— FD UI 上的"第N日"列对应 `values[N+1]`（Day N），业内"N留"对应 `values[N]`（Day N-1）
5. **`null` 是不是被当 0 算进了均值？** —— 均值要排除 null cohort

## 真实踩坑案例

某 cohort 14留 计算：

```
cohort 基数 = values[0] = 191719
错误读法 = values[13] = 87446 → 14留率 45.61%   ← 数下标错一位
正确读法 = values[14] = 85748 → 14留率 44.73%
```

两个数字看起来都"合理"（同量级、变化平缓），但分别对应 init_date+12 天 和 init_date+13 天 —— 撞到不同星期几就可能多 1~2 pp 偏差。**手数下标永远是风险**，建议在心里默念上面那条速查表再动手。
