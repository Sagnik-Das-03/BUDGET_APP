# Setting up Google Sheets sync

The app needs its own Google Cloud service account, scoped only to Sheets/Drive,
so it never touches the broad `idenza-vm` compute credential. This takes about
5 minutes.

## 1. Create (or pick) a Google Cloud project

1. Go to https://console.cloud.google.com/
2. Use an existing project, or click **New Project** (top bar) and name it
   something like `budget-tracker`.

## 2. Enable the two APIs the app needs

1. In the left sidebar: **APIs & Services > Library**
2. Search for **Google Sheets API** → click it → **Enable**
3. Search for **Google Drive API** → click it → **Enable**
   (Drive is only used to share the spreadsheet with your account after the
   service account creates it - the app never reads your other Drive files;
   its OAuth scope is `drive.file`, which only grants access to files the app
   itself created or that you've explicitly shared with it.)

## 3. Create the service account

1. **APIs & Services > Credentials**
2. **+ Create Credentials > Service account**
3. Name it `budget-tracker-sync` (or similar) → **Create and Continue**
4. **Skip** the optional "grant this service account access to project" step -
   it doesn't need any project-level IAM role, only the two API scopes above.
5. **Done**

## 4. Create and download its key

1. Click the new service account in the Credentials list
2. **Keys** tab → **Add Key > Create new key**
3. Choose **JSON** → **Create** - a `.json` file downloads

## 5. Wire it into the app

1. Move the downloaded JSON file somewhere outside this project folder, e.g.
   `C:\Users\<you>\.budget_tracker\credentials.json` - keeping credentials out
   of any folder that might later become a git repo is worth the small
   inconvenience.
2. Open `budget_tracker\.env` (copy from `.env.example` if it doesn't exist yet)
   and set:
   ```
   GOOGLE_SERVICE_ACCOUNT_KEY_PATH=C:\Users\<you>\.budget_tracker\credentials.json
   ```
3. Note the service account's email - it's the `client_email` field in the JSON
   file, something like `budget-tracker-bot@your-project.iam.gserviceaccount.com`.

## 6. Create the spreadsheet yourself and share it

**Important:** on a personal (non-Workspace) Google account, a service account
has no Drive storage of its own - it can read/write files it's given access to,
but it can't create new files. So instead of letting the app create the
spreadsheet, create it yourself:

1. Go to https://sheets.google.com and create a new blank spreadsheet, named
   e.g. "Budget Tracker"
2. Click **Share**, paste in the service account's email from step 5, give it
   **Editor** access, and uncheck "Notify people" (it's a bot, not a person)
3. Copy the spreadsheet ID out of its URL:
   `https://docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`
4. In `budget_tracker\.env`, set:
   ```
   GOOGLE_SPREADSHEET_ID=<the ID you copied>
   OWNER_EMAIL=you@gmail.com
   ```
   (`OWNER_EMAIL` isn't used for sharing in this flow since you already own the
   sheet - it's kept for reference/future features.)

(If you're on a Google Workspace account instead, the service account may be
able to create its own spreadsheet - leaving `GOOGLE_SPREADSHEET_ID` blank will
attempt that first and only falls back to needing the steps above if it's
refused.)

## 7. Run a sync

Start the app (`run.bat`), open **Settings**, and confirm "Credentials: ✓
configured" and a spreadsheet ID is set. Click **Sync Now** on any page, or
wait for the next automatic cycle. Check the **Logs** page for the result -
errors there are self-explanatory (e.g. it'll tell you directly if the sheet
isn't shared with the service account yet).

## Rotating or revoking the key later

If the key is ever exposed: **APIs & Services > Credentials**, open the service
account, **Keys** tab, delete the old key, create a new one, and update `.env`.
Deleting the key immediately revokes it - no separate "disconnect" step needed.
