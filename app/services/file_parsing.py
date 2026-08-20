"""Parse uploaded ingestion payloads into plain tables.

A "table" is deliberately dumb -- {name, headers, rows} of raw values. All the
"what does this data mean" work happens later via the LLM in
app/services/ingestion.py.
"""

import csv
import io
import json


def parse_csv(raw_bytes: bytes) -> list[dict]:
    """A CSV file is always exactly one table; first row is the header."""
    text = raw_bytes.decode("utf-8-sig")  # utf-8-sig strips a BOM if Excel added one on export
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    headers, *data_rows = rows
    return [{"name": "sheet1", "headers": headers, "rows": data_rows}]


def parse_json_records(records: list[dict]) -> list[dict]:
    """A JSON array of objects becomes one table; headers are the union of all keys seen
    across records (not just the first), so a sparse/inconsistent record shape isn't lossy."""
    if not records:
        return []
    headers = sorted({key for record in records for key in record.keys()})
    rows = [[record.get(h) for h in headers] for record in records]
    return [{"name": "table1", "headers": headers, "rows": rows}]


def parse_json(raw_bytes: bytes) -> list[dict]:
    """Accepts either a single JSON object or an array of objects; a lone object is treated
    as a one-record array."""
    payload = json.loads(raw_bytes.decode("utf-8"))
    if isinstance(payload, dict):
        payload = [payload]
    return parse_json_records(payload)


def parse_xlsx(raw_bytes: bytes) -> list[dict]:
    """One table per worksheet (unlike CSV/JSON, xlsx can carry several tables in one file);
    empty sheets are skipped. data_only=True reads formula results, not the formulas themselves."""
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(raw_bytes), data_only=True)
    tables = []
    for sheet in workbook.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        headers = [str(h) if h is not None else "" for h in rows[0]]
        data_rows = [list(row) for row in rows[1:]]
        tables.append({"name": sheet.title, "headers": headers, "rows": data_rows})
    return tables


def parse_source(source_type: str, raw_bytes: bytes | None = None, payload: list | None = None) -> list[dict]:
    """Single dispatch point used by the ingestion API regardless of upload shape (file vs.
    inline JSON/array payload)."""
    if source_type == "csv":
        return parse_csv(raw_bytes)
    if source_type == "xlsx":
        return parse_xlsx(raw_bytes)
    if source_type == "json" or source_type == "array":
        return parse_json_records(payload) if payload is not None else parse_json(raw_bytes)
    raise ValueError(f"unsupported source_type: {source_type}")
