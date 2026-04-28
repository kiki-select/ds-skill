"""
DS 取数执行脚本：调 FunnyDB skillhub analyse/query 跑 raw_sql，结果落 CSV(UTF-8 BOM)。

用法（在你的工作目录下执行）：
  python <ds-skill>/scripts/run_sql.py \
      --app-id 42 \
      --funnydb-dir <funnydb skill 路径> \
      --file queries/<场景>/main.sql \
      --out outputs/<场景>/main_<起>_<止>.csv

环境变量回退（可代替 CLI 参数）：
  FUNNYDB_APP_ID    替代 --app-id
  FUNNYDB_SKILL_DIR 替代 --funnydb-dir

平台说明：
- Windows 必须通过 Git Bash 调用 funnydb shim（shim 自身会再调 wsl）。
  Windows PATH 里的 bash 经常优先指向 WSL 的 bash.exe，会导致 shim 在 WSL
  内部找不到 wsl 命令。脚本自动定位 Git Bash；如果不在标准位置，设
  GIT_BASH 环境变量指向真实路径。
- macOS/Linux 直接用 PATH 里的 bash 即可。
"""
import argparse
import csv
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

QUERY_PATH = "/api/v1/open/skillhub/tools/analyse/query"

# Windows 上 funnydb shim 必须用 Git Bash 调用（避免 PATH 命中 WSL bash.exe）
GIT_BASH_CANDIDATES = [
    os.environ.get("GIT_BASH"),
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
]


def find_bash() -> str:
    """Pick the right bash binary for current platform."""
    if platform.system() == "Windows":
        for cand in GIT_BASH_CANDIDATES:
            if cand and Path(cand).exists():
                return cand
        found = shutil.which("bash")
        if found and "System32" not in found and "WindowsApps" not in found:
            return found
        raise RuntimeError(
            "Git Bash not found on Windows. Set GIT_BASH env var or install Git for Windows."
        )
    # macOS / Linux
    found = shutil.which("bash")
    if not found:
        raise RuntimeError("bash not found in PATH")
    return found


def run_sql(sql: str, app_id: int, funnydb_dir: str) -> dict:
    payload = {
        "app_id": app_id,
        "model": "raw_sql",
        "query": {
            "events": {"sql": sql},
            "event_view": {"variables": []},
        },
    }
    # funnydb shim 内部用 `bash -c "..."` 把参数串送入 WSL，反引号会被命令替换吃掉。
    # 把所有反引号转为 \u0060 即可让 JSON 携带字面值穿过 shell。
    payload_json = json.dumps(payload, ensure_ascii=False).replace("`", "\\u0060")

    if not Path(funnydb_dir).is_dir():
        raise RuntimeError(f"funnydb skill dir not found: {funnydb_dir}")

    result = subprocess.run(
        [find_bash(), "scripts/funnydb", "post", QUERY_PATH, "--data", payload_json],
        cwd=funnydb_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        sys.exit(result.returncode)

    try:
        resp = json.loads(result.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(f"non-JSON response from funnydb:\n{result.stdout}\n")
        sys.exit(1)

    # 两种 envelope：1) {"code":0,"data":{...}}  2) 顶层直接是 {"model":...,"result":{...}}
    if "code" in resp and resp["code"] not in (0, "0"):
        sys.stderr.write(f"FunnyDB error: {json.dumps(resp, ensure_ascii=False, indent=2)}\n")
        sys.exit(1)
    payload_data = resp.get("data", resp)
    return payload_data.get("result", payload_data)


def write_csv(data: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = data["columns"]
    col_names = [c["name"] if isinstance(c, dict) else c for c in cols]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        writer.writerows(data["rows"])


def preview(data: dict, n: int = 10) -> str:
    cols = data["columns"]
    col_names = [c["name"] if isinstance(c, dict) else c for c in cols]
    rows = data["rows"][:n]
    lines = [
        "| " + " | ".join(map(str, col_names)) + " |",
        "|" + "|".join(["---"] * len(col_names)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ClickHouse SQL via FunnyDB analyse/query.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--sql", help="Inline SQL (avoid for queries with backticks)")
    src.add_argument("--file", type=Path, help="Path to .sql file (recommended)")

    parser.add_argument("--out", type=Path, required=True, help="Output CSV path")
    parser.add_argument("--app-id", type=int, default=None,
                        help="FunnyDB app_id (or set env FUNNYDB_APP_ID)")
    parser.add_argument("--funnydb-dir", type=str, default=None,
                        help="Path to funnydb skill dir (or set env FUNNYDB_SKILL_DIR)")
    parser.add_argument("--preview-rows", type=int, default=10)

    args = parser.parse_args()

    app_id = args.app_id or os.environ.get("FUNNYDB_APP_ID")
    if not app_id:
        sys.exit("error: --app-id required (or set FUNNYDB_APP_ID env)")
    app_id = int(app_id)

    funnydb_dir = args.funnydb_dir or os.environ.get("FUNNYDB_SKILL_DIR")
    if not funnydb_dir:
        sys.exit("error: --funnydb-dir required (or set FUNNYDB_SKILL_DIR env)")

    sql = args.sql if args.sql else args.file.read_text(encoding="utf-8")
    data = run_sql(sql, app_id, funnydb_dir)
    write_csv(data, args.out)

    total = data.get("total_count")
    rows = len(data.get("rows", []))
    print(f"total_count={total} rows_returned={rows}")
    print(f"saved: {args.out}")
    print()
    print(preview(data, args.preview_rows))


if __name__ == "__main__":
    main()
