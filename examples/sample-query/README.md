# 示例查询：经典模式日均 DAU

这是一个最简化的示例，演示 ds skill 的查询目录结构约定。

## 目录约定

每个需求开一个独立子目录，文件按用途命名：

```
queries/<场景>/
  probe_<内容>.sql   # 探查脚本
  main.sql           # 最终交付的主查询
  verify_<内容>.sql  # 抽样校验脚本

outputs/<场景>/
  probe_<内容>.csv
  main_<起>_<止>.csv
  verify_<内容>.csv
```

## 本示例文件

- `probe_event_grain.sql` —— 看一条 `gameserver_login` 事件长什么样（单实体事件，pid 是数值）
- `main.sql` —— 主查询：经典模式各日 DAU
- `verify_sampling.sql` —— 抽 1 个 pid 回原始事件验证

## 运行

```bash
# 假设 ds-skill 装在 .claude/skills/ds，funnydb 装在 .claude/skills/funnydb
# 在你的工作目录下：

# 1. 探查
python .claude/skills/ds/scripts/run_sql.py \
  --app-id 42 \
  --funnydb-dir .claude/skills/funnydb \
  --file .claude/skills/ds/examples/sample-query/probe_event_grain.sql \
  --out outputs/sample/probe_event_grain.csv

# 2. 主查询
python .claude/skills/ds/scripts/run_sql.py \
  --app-id 42 \
  --funnydb-dir .claude/skills/funnydb \
  --file .claude/skills/ds/examples/sample-query/main.sql \
  --out outputs/sample/main_2026-04-14_2026-04-20.csv

# 3. 抽样校验
python .claude/skills/ds/scripts/run_sql.py \
  --app-id 42 \
  --funnydb-dir .claude/skills/funnydb \
  --file .claude/skills/ds/examples/sample-query/verify_sampling.sql \
  --out outputs/sample/verify_sampling.csv
```

> 把 `--app-id` 和 `--funnydb-dir` 换成你的实际值，或者设为环境变量 `FUNNYDB_APP_ID` / `FUNNYDB_SKILL_DIR`。
