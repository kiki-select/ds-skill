# DS Skill — 数据取数（看板优先 + 自主 SQL 兜底）

接收数据需求，**优先用 FunnyDB 看板取数**；看板覆盖不到时**自主写 ClickHouse SQL** 直接执行，结果落 UTF-8 BOM CSV 后交付（SQL + CSV 路径 + 预览 + 抽样校验摘要）。不做分析、不画图、不下结论。

触发词：`/取数`

---

## 安装

把下面这段提示词整段粘贴给你的 Claude（Claude Code 或 Claude Desktop），它会按顺序跑完所有步骤：

```
ds 是一个 Agent Skills，请按以下步骤依次帮我安装，每步执行完再进下一步，遇到错误立即停下并告知我：

1. 找到本地 skills 目录（项目级通常是 .claude/skills/，全局是 ~/.claude/skills/）

2. clone 仓库：
   git clone https://github.com/kiki-select/ds-skill.git ds

3. 安装数据源 skill funnydb（在同一个 skills 目录下）：
   git clone https://git.sofunny.io/data-analysis/funnydb-skills.git funnydb
   注：Windows 用户如果没装 WSL，先跑 `wsl --install --web-download`，重启后再继续这一步。新版 funnydb 自动授权，无需手动配置 API Key。

4. 验证 funnydb 已通：
   cd funnydb && bash scripts/funnydb post /api/v1/open/skillhub/tools/apps/list
   能列出有权限的 app 列表即成功。记下你要查的 app_id。

5. 全部完成后输出确认，并简单提示我下一步可以用 `/取数` 触发工作流，需要告诉 ds 你的 app_id。
```

### 非 Claude Code 用户（Codex / OpenCode / Aider 等）

Agent Skills 的 `name:` frontmatter + `/<skill>` 触发语法是 Claude 生态特有，但本仓库可以无缝降级：

1. **安装位置随意**：`git clone` 到任何目录都行（不需要 `.claude/skills/`）
2. **让 Agent 读 SKILL.md**：把 `SKILL.md` 当作工作流说明书。常见做法：
   - Codex / OpenCode：项目根放一份 `AGENTS.md` 软链到 `SKILL.md`（`ln -s SKILL.md AGENTS.md`）
   - 其他工具：让 Agent 第一步 `cat SKILL.md` 读一遍
3. **触发方式改成自然语言**：「按 SKILL.md 流程帮我取一下 X 数据，app_id 是 42」
4. **`scripts/run_sql.py` 是纯 Python 脚本**，任何工具甚至不带 Agent 都能 `python scripts/run_sql.py --app-id ... --file query.sql --out result.csv` 直接跑

---

## 前置依赖

### 1. 运行环境

- **Python ≥ 3.8**
- **funnydb skill** 已安装且授权可用

### 2. funnydb skill

本 skill 完全依赖 funnydb 做数据通道（看板查询 + raw SQL 执行）。

#### macOS / Linux 安装

```
funnydb-skills 是一个 Agent Skills，把它 clone 到你的 skills 目录：

git clone https://git.sofunny.io/data-analysis/funnydb-skills.git funnydb
```

新版 funnydb 已支持自动授权验证，**不需要手动配置 API Key**。

验证：

```bash
cd <skills目录>/funnydb
bash scripts/funnydb post /api/v1/open/skillhub/tools/apps/list
# 能列出有权限的 app 列表即成功
```

#### Windows：通过 WSL 桥接

**funnydb-cli 二进制只发 Linux/macOS 版本，Windows 必须通过 WSL 跑**。funnydb 仓库自带 `scripts/funnydb` 是 Windows 侧的 shim，自动把调用转发进 WSL。

```powershell
# 1. 启用 WSL（管理员 PowerShell，未装过的话）
wsl --install --web-download
# --web-download 直接从 GitHub 下载，绕过 Microsoft Store
# 重启电脑后默认装 Ubuntu
```

> ⚠️ 不加 `--web-download` 会走 Microsoft Store，公司机器常被组策略/代理拦截返回 403。

```powershell
# 2. 进 WSL，准备依赖
wsl
sudo apt update && sudo apt install -y curl unzip

# 3. 回 Git Bash，clone funnydb skill
cd <skills目录>
git clone https://git.sofunny.io/data-analysis/funnydb-skills.git funnydb
```

`run_sql.py` 自动定位 Git Bash 调用 funnydb shim（避免 PATH 命中 WSL 的 bash.exe）。如果 Git Bash 不在标准路径，设环境变量：

```bash
export GIT_BASH="/c/Program Files/Git/usr/bin/bash.exe"
```

---

## 使用

### 触发方式

跟你的 Claude 说：

```
/取数
```

或直接表达意图：

> 帮我跑一下 4/14-4/20 经典模式各服务器的日均 DAU，app_id 42

Claude 会按 SKILL.md 中的 8 步流程走：

1. **拆需求** —— 四要素（指标/维度/时间/过滤），不清晰就问
2. **找看板** —— `dashboards/search` 拉目录，按业务关键词找候选；满足就直接 `panels/data` 拉数
3. **元数据查询** —— 看板不满足才走自主 SQL；先 `analyse/properties` 拿字段定义
4. **数据探查** —— 实体粒度识别 + 验聚合键唯一性 + 看枚举分布
5. **写 SQL** —— 按 ClickHouse 规范写静态日期 SQL
6. **执行** —— `run_sql.py` 跑出结果
7. **抽样校验** —— 挑 1~3 个用户/维度回原始事件比对
8. **落 CSV + 交付** —— SQL + 路径 + 预览 + 校验摘要

### 直接调用脚本

跳过 AI 流程，自己写好 SQL 后直接跑：

```bash
python scripts/run_sql.py \
  --app-id 42 \
  --funnydb-dir <funnydb skill 路径> \
  --file queries/my-query/main.sql \
  --out outputs/my-query/result_2026-04-14_2026-04-20.csv
```

或用环境变量减少重复参数：

```bash
export FUNNYDB_APP_ID=42
export FUNNYDB_SKILL_DIR=/path/to/funnydb

python scripts/run_sql.py --file queries/x/main.sql --out outputs/x/result.csv
```

输出：`total_count` + 写入路径 + 前 10 行 Markdown 预览。

---

## 目录结构

```
ds/
├── SKILL.md                                  # 工作流入口（触发后 Claude 跟随）
├── README.md                                 # 本文件
├── LICENSE
├── scripts/
│   └── run_sql.py                            # FunnyDB analyse/query 执行器
├── references/
│   ├── clickhouse-sql-conventions.md         # SQL 书写规范（缩进/命名/铁律）
│   ├── data-probing-templates.md             # 探查 SQL 模板集
│   ├── entity-grain-identification.md        # 实体粒度识别（pid_list 陷阱）
│   └── result-verification.md                # 抽样校验方法论
├── examples/
│   └── sample-query/                         # 示例查询（main.sql + probe + verify）
├── queries/                                  # 你的 SQL（运行时创建，按场景分子目录）
└── outputs/                                  # 你的 CSV（运行时创建，按场景分子目录）
```

---

## 核心特性

### 1. 看板优先 + SQL 兜底

不重复造轮子：先查 FunnyDB 现成看板，覆盖不到才自己写 SQL。决策树清晰，不会一上来就乱写 SQL。

### 2. 全流程归档（决策链路可追溯）

每个需求一个独立子目录：`probe_*.sql` 探查、`main.sql` 主查询、`verify_*.sql` 校验，**跑完不删**。后续看的人能从演进过程理解为什么主查询是这么写的。

### 3. 强制实体粒度识别

主查询前必跑 `limit 3` 看事件长什么样，识别单实体 vs 批量上报（pid_list）。**避免把事件粒度成功率当玩家粒度成功率交付**这种隐性错误。

### 4. 强制抽样校验

主查询跑完抽 1~3 个用户回原始事件手算比对。聚合 SQL 写对≠语义对，抽样校验是发现「漏 NULL / 双计 stat / 跨天事件并到一天」这类错误最便宜的手段。

### 5. CSV 自带 UTF-8 BOM

Windows Excel 直接打开不乱码。

---

## 常见问题

| 问题 | 解决 |
|---|---|
| `funnydb skill dir not found` | `--funnydb-dir` 路径错，确认 funnydb 实际安装位置 |
| `--app-id required` | 加 `--app-id <N>` 或设 `FUNNYDB_APP_ID` 环境变量 |
| `Git Bash not found on Windows` | 装 Git for Windows，或设 `GIT_BASH` 环境变量指向 bash.exe 真实路径 |
| funnydb 调用 hang 住 / 授权失败 | 删 funnydb skill 目录下 `.bin/` 让 CLI 重新下载二进制；如仍有问题按 funnydb skill 提示重新走授权 |
| `wsl --install` 报 403 / 卡 Store | 改用 `wsl --install --web-download` 从 GitHub 直接拉 |
| ClickHouse JOIN 报错 | 检查 `on` 子句是否写了 `>=` / `between`，必须只写等值条件 |
| SQL 反引号被 shell 吞掉 | 必须 `--file` 传 `.sql` 文件，**不要** `--sql` inline 含反引号的 SQL |
| 中文 CSV 乱码 | 确认写 CSV 用了 `utf-8-sig` 编码（脚本已自动） |
| 0 行结果 | 单独跑 count 确认事件名+日期范围对不对 |
| 行数巨多 | 检查 join 是否漏等值、group by 是否漏维度 |

更多踩坑速查见 [SKILL.md](SKILL.md) 末尾。

---

## 工作流速查

```
拿到需求
  │
  ├─ Step 1：拆四要素（指标/维度/时间/过滤），不清晰回问
  │
  ├─ Step 2：dashboards/search 拉看板目录，按业务关键词找候选
  │   │
  │   ├─ 看板口径精确匹配 → panels/data 拉数据 → Step 8 落 CSV
  │   └─ 没看板 / 口径不匹配 → 进 Step 3
  │
  ├─ Step 3：analyse/events + analyse/properties 查埋点元数据
  ├─ Step 4：实体粒度识别 + 探查模板验证假设
  ├─ Step 5：写静态日期 SQL
  ├─ Step 6：run_sql.py 执行
  ├─ Step 7：抽样校验
  └─ Step 8：落 CSV + 交付（SQL + 路径 + 预览 + 校验摘要）
```

---

## License

MIT
