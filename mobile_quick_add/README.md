# Mobile quick-add form

A phone-friendly "add transaction" page that writes straight to the Google Sheet
Budget Tracker syncs with — no backend, no PC needed. Google hosts it for free.

How it connects to the app: it appends a row with a **blank Transaction ID**.
The app's sync engine already treats that as "new row from the sheet" — on the
next sync it assigns a real ID, fills in the Month column, and pulls it into
your local database, exactly like editing the sheet by hand would. Nothing in
the backend or frontend needed to change for this to work.

It's still add-only, not a mobile dashboard — no charts, no editing existing
transactions. What it does show, read straight off the sheet on page load and
refreshed after every add: this calendar month's Income/Expenses/Net, and the
8 most recent transactions (deleted rows excluded from both). Enough to
sanity-check "did that last entry actually go through" without opening the
full app.

## Deploy it (one-time, ~5 minutes)

1. Open your Budget Tracker spreadsheet in Google Sheets (the one at
   `GOOGLE_SPREADSHEET_ID` in `backend/.env`).
2. **Extensions → Apps Script**. This opens a script editor already bound to
   your spreadsheet.
3. Delete whatever's in the default `Code.gs` file, and paste in the contents
   of this folder's `Code.gs`.
4. **File → New → HTML**, name it exactly `Form` (Apps Script adds the `.html`
   itself). Paste in the contents of this folder's `Form.html`.
5. Save the project (the disk icon, or Ctrl+S).
6. **Deploy → New deployment**. Click the gear next to "Select type" and
   choose **Web app**.
   - Description: `Quick add` (or anything).
   - Execute as: **Me**.
   - Who has access: **Only myself** — recommended. You'll already be signed
     into your own Google account on your phone, so this adds no real
     friction, and it's the only setting that keeps the form private to you.
     ("Anyone with the link" skips the sign-in prompt but means literally
     anyone who gets hold of the URL can add rows to your sheet — avoid it
     unless you have a specific reason.)
7. Click **Deploy**. The first time, Google shows an "unverified app" consent
   screen since this is your own personal script — click **Advanced → Go to
   (your project name)** and allow it. This is normal for scripts you write
   yourself, not a red flag.
8. Copy the **Web app URL** it gives you.

## Add it to your phone

Open that URL in your phone's browser, then:
- **iOS Safari**: Share icon → "Add to Home Screen"
- **Android Chrome**: ⋮ menu → "Add to Home Screen" / "Install app"

It'll sit on your home screen with its own icon, opening straight to the form.

## Updating it later

If you edit `Code.gs` or `Form.html` (in the script editor or by re-pasting
updated versions from this folder), the changes **don't** go live automatically
— Apps Script web apps are versioned. Go to **Deploy → Manage deployments**,
click the pencil icon on the existing deployment, and choose **New version**
under "Version," then **Deploy**. The URL and home-screen shortcut stay the
same; only the code behind it updates.

## Verifying it worked

1. Submit a test transaction from the form.
2. Check the spreadsheet — a new row should appear with the Transaction ID
   column blank.
3. Either wait for the app's normal sync interval, or trigger one immediately
   from Settings → Sync now (or the Dashboard's sync widget). The row should
   pick up a real `TXN-YYYY-######` ID and show up in Transactions/Dashboard.
