"""In-memory fake of GoogleSheetsService's interface - lets the sync engine and
reports be tested without any real network/API calls (spec section 29)."""
from dataclasses import dataclass, field


@dataclass
class FakeSheetInfo:
    title: str
    sheet_id: int


class FakeGoogleSheetsService:
    def __init__(self):
        self._next_sheet_id = 1
        self.sheets: dict[str, int] = {}
        self.values: dict[str, list[list]] = {}
        self.charts: dict[int, list[int]] = {}
        self._next_chart_id = 1
        self.spreadsheets: dict[str, str] = {}
        self.shares: list[tuple] = []

    # ---------- spreadsheet-level ----------

    def create_spreadsheet(self, title: str) -> str:
        sid = f"fake-spreadsheet-{len(self.spreadsheets) + 1}"
        self.spreadsheets[sid] = title
        self.ensure_sheet(sid, "Transactions")
        return sid

    def share_with(self, spreadsheet_id: str, email: str, role: str = "writer") -> None:
        self.shares.append((spreadsheet_id, email, role))

    def get_sheets(self, spreadsheet_id: str):
        return [FakeSheetInfo(title=t, sheet_id=i) for t, i in self.sheets.items()]

    def spreadsheet_url(self, spreadsheet_id: str) -> str:
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"

    # ---------- sheet management ----------

    def create_sheet(self, spreadsheet_id: str, title: str, rows: int = 2000, cols: int = 16) -> int:
        sid = self._next_sheet_id
        self._next_sheet_id += 1
        self.sheets[title] = sid
        self.values[title] = []
        self.charts[sid] = []
        return sid

    def ensure_sheet(self, spreadsheet_id: str, title: str) -> int:
        if title in self.sheets:
            return self.sheets[title]
        return self.create_sheet(spreadsheet_id, title)

    # ---------- values ----------

    def get_rows(self, spreadsheet_id: str, sheet_name: str) -> list[list]:
        return [list(row) for row in self.values.get(sheet_name, [])]

    def append_rows(self, spreadsheet_id: str, sheet_name: str, rows: list[list]) -> None:
        self.values.setdefault(sheet_name, []).extend([list(r) for r in rows])

    def update_rows(self, spreadsheet_id: str, sheet_name: str, row_updates: dict) -> None:
        data = self.values.setdefault(sheet_name, [])
        for row_num, values in row_updates.items():
            idx = row_num - 1
            while len(data) <= idx:
                data.append([])
            data[idx] = list(values)

    def clear_and_write(self, spreadsheet_id: str, sheet_name: str, rows: list[list]) -> None:
        self.values[sheet_name] = [list(r) for r in rows]

    # ---------- formatting / charts ----------

    def batch_format(self, spreadsheet_id: str, requests: list[dict]) -> None:
        for req in requests:
            if "addChart" in req:
                sheet_id = req["addChart"]["chart"]["spec"].get("_sheet_id")
            if "deleteEmbeddedObject" in req:
                obj_id = req["deleteEmbeddedObject"]["objectId"]
                for sid, ids in self.charts.items():
                    if obj_id in ids:
                        ids.remove(obj_id)

    def get_chart_ids(self, spreadsheet_id: str, sheet_id: int) -> list[int]:
        return list(self.charts.get(sheet_id, []))

    def delete_charts(self, spreadsheet_id: str, chart_ids: list[int]) -> None:
        for sid, ids in self.charts.items():
            self.charts[sid] = [i for i in ids if i not in chart_ids]
