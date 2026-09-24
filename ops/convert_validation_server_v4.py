#!/usr/bin/env python3
"""Convert validation_test_set.xlsx to eval.jsonl format for wenshu-agent evaluation.

This script runs on the server where the database is accessible.
It executes gold_sql to generate gold_answer for each record.

Usage:
    python3 convert_validation_server.py [--limit N] [--offset N] [--output PATH]
"""

import argparse
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path

# Add wenshu_agent code to path for db access
sys.path.insert(0, "/home/test/wenshu_agent/code")
from db import connect


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        from datetime import date, datetime, time
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, time):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        return super().default(obj)


def read_xlsx(path: str) -> list[dict]:
    """Read xlsx file without pandas/openpyxl."""
    z = zipfile.ZipFile(path)

    # shared strings
    ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for si in ss.findall("main:si", ns):
        text = "".join(
            t.text or ""
            for t in si.iter(
                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"
            )
        )
        strings.append(text)

    # sheet
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = sheet.find("main:sheetData", ns).findall("main:row", ns)

    data = []
    headers = []
    for i, row in enumerate(rows):
        vals = []
        for c in row.findall("main:c", ns):
            t = c.get("t")
            v = c.find("main:v", ns)
            if v is None:
                vals.append("")
                continue
            val = v.text
            if t == "s":
                val = strings[int(val)]
            vals.append(val)

        if i == 0:
            headers = vals
            continue

        record = {}
        for j, h in enumerate(headers):
            if h and j < len(vals):
                record[h] = vals[j]
        data.append(record)

    return data


def extract_pre_sqls(pre_sql_text: str) -> list[str]:
    """Extract individual pre-SQL statements from the text."""
    if not pre_sql_text or not pre_sql_text.strip():
        return []

    # Split by "前置" or "前置N：" pattern
    parts = re.split(r"前置\d*[：:]", pre_sql_text)
    sqls = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Remove leading description line (e.g., "查询企业ID：")
        lines = part.split("\n")
        if lines and not lines[0].strip().upper().startswith(("SELECT", "WITH")):
            lines = lines[1:]
        sql = "\n".join(lines).strip()
        if sql and sql.upper().startswith(("SELECT", "WITH")):
            sqls.append(sql)
    return sqls


def clean_sql(sql: str) -> str:
    """Clean SQL: extract only the first SELECT statement.

    The input may contain multiple SELECT statements separated by -- comments.
    We only keep the first one for evaluation.
    """
    if not sql:
        return ""

    # Normalize line endings
    sql = sql.replace("\r\n", "\n").replace("\r", "\n")

    # Find all SELECT/WITH statement start positions
    lines = sql.split("\n")
    select_starts = []
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped.startswith("SELECT") or stripped.startswith("WITH"):
            select_starts.append(i)

    if not select_starts:
        return ""

    # Take only the first statement
    start_idx = select_starts[0]

    # Find where the first statement ends
    # It ends at the next -- comment that is followed by another SELECT,
    # or at the end of input
    end_idx = len(lines)

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()

        # Check if this is a -- comment line
        if stripped.startswith("--"):
            # Look ahead to see if next non-empty line starts a new SELECT
            for j in range(i + 1, len(lines)):
                next_stripped = lines[j].strip().upper()
                if not next_stripped:
                    continue
                if next_stripped.startswith("SELECT") or next_stripped.startswith("WITH"):
                    # Found a new statement, end the first one here
                    end_idx = i
                    break
                else:
                    # Not a new statement, continue
                    break
            if end_idx != len(lines):
                break

    # Extract the first statement
    result_lines = lines[start_idx:end_idx]
    sql = "\n".join(result_lines)

    # Remove -- comments
    sql = re.sub(r"--.*?(?=\n|$)", " ", sql)
    # Remove /* */ comments
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    # Normalize whitespace
    sql = re.sub(r"\s+", " ", sql)
    return sql.strip()


def execute_sql(sql: str, max_rows: int = 500, timeout_ms: int = 30_000) -> dict:
    """Execute SQL and return result in gold_answer format."""
    if not sql or not sql.strip():
        return {"ok": False, "error": "empty sql", "columns": [], "rows": [], "row_count": 0}

    try:
        conn = connect(statement_timeout_ms=timeout_ms)
        cur = conn.cursor()
        cur.execute(sql)
        try:
            rows = cur.fetchmany(max_rows)
            cols = [d.name for d in cur.description] if cur.description else []
        except Exception:
            rows, cols = [], []
        cur.close()
        conn.close()
        return {
            "ok": True,
            "columns": cols,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated_at": max_rows if len(rows) >= max_rows else 0,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e).strip().splitlines()[0][:300],
            "columns": [],
            "rows": [],
            "row_count": 0,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of records to process")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N records")
    parser.add_argument("--output", type=str, default="/home/test/wenshu_agent/data/final/validation_eval.jsonl")
    parser.add_argument("--timeout", type=int, default=60, help="SQL timeout in seconds")
    args = parser.parse_args()

    input_path = Path("/home/test/validation_test_set.xlsx")
    output_path = Path(args.output)

    print(f"Reading {input_path}...")
    records = read_xlsx(str(input_path))
    print(f"Loaded {len(records)} records")

    # Apply offset and limit
    if args.offset:
        records = records[args.offset:]
    if args.limit:
        records = records[:args.limit]

    print(f"Processing {len(records)} records (offset={args.offset}, limit={args.limit})")

    eval_records = []
    stats = {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    for idx, r in enumerate(records):
        question = r.get("问题", "").strip()
        if not question:
            stats["skipped"] += 1
            continue

        pre_sql_text = r.get("SQL前置", "").strip()
        main_sql = r.get("使用SQL", "").strip()

        # Clean main SQL
        main_sql_clean = clean_sql(main_sql)
        if not main_sql_clean:
            print(f"[{idx+1}/{len(records)}] id={r.get('问题序号', '')}: SKIPPED (no valid SQL)")
            stats["skipped"] += 1
            continue

        rid = r.get("问题序号", "")
        print(f"[{idx+1}/{len(records)}] id={rid}: {question[:60]}...")

        # Execute gold SQL to get gold_answer
        gold_answer = execute_sql(main_sql_clean, timeout_ms=args.timeout * 1000)

        if not gold_answer["ok"]:
            print(f"  FAILED: {gold_answer['error'][:100]}")
            stats["failed"] += 1
        else:
            print(f"  OK: {gold_answer['row_count']} rows")
            stats["success"] += 1

        pre_sqls = extract_pre_sqls(pre_sql_text)

        record = {
            "id": f"val-{rid}",
            "source": "validation_test_set",
            "module": r.get("查询功能模块", "").strip(),
            "condition": r.get("查询条件/维度", "").strip(),
            "remark": r.get("备注", "").strip(),
            "question": question,
            "gold_sql": main_sql_clean,
            "gold_answer": gold_answer,
            "pre_sql": pre_sqls,
        }
        eval_records.append(record)
        stats["total"] += 1

    # Write JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for r in eval_records:
            f.write(json.dumps(r, ensure_ascii=False, cls=DecimalEncoder) + "\n")

    print(f"\n=== Statistics ===")
    print(f"Total processed: {stats['total']}")
    print(f"Successful gold execution: {stats['success']}")
    print(f"Failed gold execution: {stats['failed']}")
    print(f"Skipped (empty): {stats['skipped']}")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
