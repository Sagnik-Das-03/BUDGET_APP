"""A minimal, read-only-ONLY Google Sheets client for the Android dashboard
viewer. Deliberately does NOT reuse backend/app/sheets/adapter.py's
GoogleSheetsService - that class has create/delete/write methods and
requests the full read-write `spreadsheets` + `drive.file` scopes, since the
desktop app's sync engine needs them. This build should have no way to even
ACCIDENTALLY write, not just a policy of never calling a write method - so
it gets its own client with only a read method and only the read-only scope.

Real enforcement of "read-only" is the spreadsheet's sharing permission
(Viewer, not Editor) on whichever service account's key this points at -
the scope requested here is a second, defense-in-depth layer on top of
that, not a substitute for it. See docs/service_account_setup.md for how
the desktop sync's own (read-write) service account was set up; this needs
a SEPARATE service account, shared as Viewer, with its own key file.
"""
from google.oauth2 import service_account
from googleapiclient.discovery import build

READ_ONLY_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class ReadOnlySheetsClient:
    def __init__(self, credentials_path: str):
        creds = service_account.Credentials.from_service_account_file(credentials_path, scopes=READ_ONLY_SCOPES)
        self._sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)

    def get_rows(self, spreadsheet_id: str, sheet_name: str) -> list[list[str]]:
        """Every data row (row 2 onward - row 1 is the header) from a tab,
        as raw strings, same shape app/sheets/mapping.py's parse_row expects."""
        result = self._sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A2:Z",
        ).execute()
        return result.get("values", [])
