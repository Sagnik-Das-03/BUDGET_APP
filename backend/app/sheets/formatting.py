"""Generic Sheets API request builders for human-readable generated tabs:
bold headers, currency number formats, frozen header row, and native charts."""

INK = {"red": 0.043, "green": 0.043, "blue": 0.043}
WHITE = {"red": 1, "green": 1, "blue": 1}
HEADER_BG = {"red": 0.32, "green": 0.32, "blue": 0.30}


def _hex_to_rgb(hex_color: str) -> dict:
    h = hex_color.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


def bold_header_request(sheet_id: int, row0: int, num_cols: int) -> dict:
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row0, "endRowIndex": row0 + 1,
                      "startColumnIndex": 0, "endColumnIndex": num_cols},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True, "foregroundColor": WHITE},
                "backgroundColor": HEADER_BG,
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment)",
        }
    }


def title_request(sheet_id: int, row0: int, size: int = 16) -> dict:
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row0, "endRowIndex": row0 + 1,
                      "startColumnIndex": 0, "endColumnIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": size}}},
            "fields": "userEnteredFormat.textFormat",
        }
    }


def freeze_row_request(sheet_id: int, count: int = 1) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": count}},
            "fields": "gridProperties.frozenRowCount",
        }
    }


def currency_format_request(sheet_id: int, row_start0: int, row_end0: int, col_start0: int, col_end0: int) -> dict:
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row_start0, "endRowIndex": row_end0,
                      "startColumnIndex": col_start0, "endColumnIndex": col_end0},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": "₹#,##0.00"}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def plain_number_format_request(sheet_id: int, row_start0: int, row_end0: int, col_start0: int, col_end0: int) -> dict:
    """A currency symbol on the Amount column looks nice on the read-only
    generated report tabs, but on the editable Transactions tab it meant a
    value typed directly into the sheet came back from the API pre-formatted
    (e.g. "₹2,000.00") and had to be stripped back out before parsing - this
    keeps that column's cells as a plain number instead."""
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row_start0, "endRowIndex": row_end0,
                      "startColumnIndex": col_start0, "endColumnIndex": col_end0},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def data_row_text_color_request(sheet_id: int, num_cols: int, row_start0: int = 1, row_end0: int = 5000) -> dict:
    """Forces data-row text to plain black (INK), so it stays readable
    regardless of whatever the text color happened to default to - a
    manually-typed row can inherit odd formatting from wherever it was
    typed or pasted from."""
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row_start0, "endRowIndex": row_end0,
                      "startColumnIndex": 0, "endColumnIndex": num_cols},
            "cell": {"userEnteredFormat": {"textFormat": {"foregroundColor": INK}}},
            "fields": "userEnteredFormat.textFormat.foregroundColor",
        }
    }


def column_alignment_request(sheet_id: int, row_start0: int, row_end0: int, col0: int, alignment: str) -> dict:
    """alignment: "LEFT" | "CENTER" | "RIGHT"."""
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row_start0, "endRowIndex": row_end0,
                      "startColumnIndex": col0, "endColumnIndex": col0 + 1},
            "cell": {"userEnteredFormat": {"horizontalAlignment": alignment}},
            "fields": "userEnteredFormat.horizontalAlignment",
        }
    }


def column_width_request(sheet_id: int, col0: int, width: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": col0, "endIndex": col0 + 1},
            "properties": {"pixelSize": width},
            "fields": "pixelSize",
        }
    }


def basic_chart_request(
    *, sheet_id: int, chart_type: str, title: str, domain_col0: int, series_cols0: list[int],
    row_start0: int, row_end0: int, series_names: list[str], series_colors: list[str],
    anchor_row0: int, anchor_col0: int, stacked: bool = False, horizontal: bool = False,
) -> dict:
    domain = {
        "domain": {"sourceRange": {"sources": [{
            "sheetId": sheet_id, "startRowIndex": row_start0, "endRowIndex": row_end0,
            "startColumnIndex": domain_col0, "endColumnIndex": domain_col0 + 1,
        }]}}
    }
    series = []
    for col0, name, color in zip(series_cols0, series_names, series_colors):
        series.append({
            "series": {"sourceRange": {"sources": [{
                "sheetId": sheet_id, "startRowIndex": row_start0, "endRowIndex": row_end0,
                "startColumnIndex": col0, "endColumnIndex": col0 + 1,
            }]}},
            "targetAxis": "LEFT_AXIS",
            "color": _hex_to_rgb(color),
        })

    spec: dict = {
        "title": title,
        "basicChart": {
            "chartType": chart_type,
            "legendPosition": "BOTTOM_LEGEND",
            "axis": [{"position": "BOTTOM_AXIS"}, {"position": "LEFT_AXIS"}],
            "domains": [domain],
            "series": series,
            "headerCount": 1,
        },
    }
    if stacked:
        spec["basicChart"]["stackedType"] = "STACKED"
    if horizontal:
        spec["basicChart"]["chartType"] = "BAR"

    return {
        "addChart": {
            "chart": {
                "spec": spec,
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row0, "columnIndex": anchor_col0},
                        "offsetXPixels": 0, "offsetYPixels": 0, "widthPixels": 640, "heightPixels": 360,
                    }
                },
            }
        }
    }
