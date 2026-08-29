"""All Google Sheets/Drive API calls live here and ONLY here (spec section 25).
The rest of the app talks to GoogleSheetsService, never to googleapiclient directly.
"""
import time
from dataclasses import dataclass
from typing import Optional, Any, Callable, TypeVar

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

T = TypeVar("T")


def with_retry(fn: Callable[[], T], *, retries: int = 4, base_delay: float = 1.5,
               on_retry: Optional[Callable[[int, Exception], None]] = None) -> T:
    """Exponential backoff for transient API/network failures (spec section 21)."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except HttpError as e:
            last_exc = e
            transient = e.resp.status in (429, 500, 502, 503, 504) if getattr(e, "resp", None) else True
            if not transient or attempt == retries:
                raise
        except Exception as e:  # network errors, etc.
            last_exc = e
            if attempt == retries:
                raise
        if on_retry:
            on_retry(attempt, last_exc)
        time.sleep(base_delay * (2 ** attempt))
    raise last_exc  # pragma: no cover


@dataclass
class SheetInfo:
    title: str
    sheet_id: int


class GoogleSheetsService:
    def __init__(self, credentials_path: str):
        creds = service_account.Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        self._sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
        self._drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.service_account_email = creds.service_account_email

    # ---------- spreadsheet-level ----------

    def create_spreadsheet(self, title: str) -> str:
        body = {"properties": {"title": title}, "sheets": [{"properties": {"title": "Transactions"}}]}
        result = with_retry(lambda: self._sheets.spreadsheets().create(body=body).execute())
        return result["spreadsheetId"]

    def share_with(self, spreadsheet_id: str, email: str, role: str = "writer") -> None:
        body = {"type": "user", "role": role, "emailAddress": email}
        with_retry(lambda: self._drive.permissions().create(
            fileId=spreadsheet_id, body=body, sendNotificationEmail=False,
        ).execute())

    def get_sheets(self, spreadsheet_id: str) -> list[SheetInfo]:
        meta = with_retry(lambda: self._sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute())
        return [SheetInfo(title=s["properties"]["title"], sheet_id=s["properties"]["sheetId"])
                for s in meta.get("sheets", [])]

    def spreadsheet_url(self, spreadsheet_id: str) -> str:
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    # ---------- sheet (tab) management ----------

    def create_sheet(self, spreadsheet_id: str, title: str, rows: int = 2000, cols: int = 16) -> int:
        body = {"requests": [{"addSheet": {"properties": {
            "title": title, "gridProperties": {"rowCount": rows, "columnCount": cols},
        }}}]}
        result = with_retry(lambda: self._sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body).execute())
        return result["replies"][0]["addSheet"]["properties"]["sheetId"]

    def ensure_sheet(self, spreadsheet_id: str, title: str) -> int:
        for s in self.get_sheets(spreadsheet_id):
            if s.title == title:
                return s.sheet_id
        return self.create_sheet(spreadsheet_id, title)

    # ---------- values ----------

    def get_rows(self, spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
        rng = f"'{sheet_name}'!A1:Z100000"
        result = with_retry(lambda: self._sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=rng).execute())
        return result.get("values", [])

    def append_rows(self, spreadsheet_id: str, sheet_name: str, rows: list[list[Any]]) -> None:
        if not rows:
            return
        rng = f"'{sheet_name}'!A1"
        body = {"values": rows}
        with_retry(lambda: self._sheets.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range=rng, valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS", body=body).execute())

    def update_rows(self, spreadsheet_id: str, sheet_name: str, row_updates: dict[int, list[Any]]) -> None:
        """row_updates: {row_number (1-indexed, sheet row) -> full row values starting at column A}."""
        if not row_updates:
            return
        data = [
            {"range": f"'{sheet_name}'!A{row_num}", "values": [values]}
            for row_num, values in row_updates.items()
        ]
        body = {"valueInputOption": "USER_ENTERED", "data": data}
        with_retry(lambda: self._sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body).execute())

    def clear_and_write(self, spreadsheet_id: str, sheet_name: str, rows: list[list[Any]]) -> None:
        """Full-tab regeneration used by report tabs (monthly/weekly/yearly/Dashboard) -
        always rewritten wholesale from the DB, never incrementally patched."""
        rng = f"'{sheet_name}'!A1:Z100000"
        with_retry(lambda: self._sheets.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=rng, body={}).execute())
        if rows:
            with_retry(lambda: self._sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'!A1",
                valueInputOption="USER_ENTERED", body={"values": rows}).execute())

    # ---------- formatting / charts (human-readable reports) ----------

    def batch_format(self, spreadsheet_id: str, requests: list[dict]) -> None:
        if not requests:
            return
        with_retry(lambda: self._sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}).execute())

    def get_chart_ids(self, spreadsheet_id: str, sheet_id: int) -> list[int]:
        meta = with_retry(lambda: self._sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id, fields="sheets(properties.sheetId,charts.chartId)").execute())
        for s in meta.get("sheets", []):
            if s["properties"]["sheetId"] == sheet_id:
                return [c["chartId"] for c in s.get("charts", [])]
        return []

    def delete_charts(self, spreadsheet_id: str, chart_ids: list[int]) -> None:
        if not chart_ids:
            return
        requests = [{"deleteEmbeddedObject": {"objectId": cid}} for cid in chart_ids]
        self.batch_format(spreadsheet_id, requests)
