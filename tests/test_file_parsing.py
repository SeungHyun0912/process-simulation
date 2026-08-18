import io

from app.services.file_parsing import parse_csv, parse_json_records, parse_xlsx


def test_parse_csv():
    raw = b"product_id,product_name\nCV-1,Cable One\nCV-2,Cable Two\n"
    tables = parse_csv(raw)
    assert len(tables) == 1
    assert tables[0]["headers"] == ["product_id", "product_name"]
    assert tables[0]["rows"] == [["CV-1", "Cable One"], ["CV-2", "Cable Two"]]


def test_parse_json_records_fills_missing_keys_with_none():
    records = [{"product_id": "CV-1", "product_name": "Cable One"}, {"product_id": "CV-2"}]
    tables = parse_json_records(records)
    assert tables[0]["headers"] == ["product_id", "product_name"]
    assert tables[0]["rows"][1] == ["CV-2", None]


def test_parse_xlsx_reads_sheet_name_and_rows():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Products"
    sheet.append(["product_id", "product_name"])
    sheet.append(["CV-1", "Cable One"])
    buf = io.BytesIO()
    workbook.save(buf)

    tables = parse_xlsx(buf.getvalue())

    assert tables[0]["name"] == "Products"
    assert tables[0]["headers"] == ["product_id", "product_name"]
    assert tables[0]["rows"] == [["CV-1", "Cable One"]]
