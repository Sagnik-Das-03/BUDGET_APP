/**
 * Mobile quick-add form for Budget Tracker, bound to the same spreadsheet the
 * app syncs with. Deployed as a standalone Web App (see README.md) - it never
 * touches the FastAPI backend, so it works even when your PC is off.
 *
 * How this reaches the app: it appends a row with a BLANK Transaction ID. The
 * app's sync engine (backend/app/sync/engine.py, pull()) already treats a
 * blank ID as "new row from the sheet" - it assigns a real TXN-YYYY-###### id,
 * rewrites the cell, and reconciles it into the local database on the very
 * next sync cycle. Same for the Month column - the app fills that in too.
 *
 * Editing an existing row deliberately leaves its Transaction ID (and Month,
 * Deleted) cells untouched - only Date/Description/Category/Account/Amount/
 * Type/Notes are overwritten. Changing the ID would make the sync engine treat
 * an edit as a brand new transaction instead of an update to the existing one.
 *
 * Column order must match backend/app/sheets/mapping.py's HEADERS exactly:
 *   Transaction ID | Date | Description | Category | Account | Amount | Type | Month | Notes | Deleted
 */

const SHEET_NAME = 'Transactions';

function doGet() {
  return HtmlService.createHtmlOutputFromFile('Form')
    .setTitle('Add Transaction')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1, maximum-scale=1');
}

function headerIndex_(sheet) {
  const header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  return {
    id: header.indexOf('Transaction ID'),
    date: header.indexOf('Date'),
    description: header.indexOf('Description'),
    category: header.indexOf('Category'),
    account: header.indexOf('Account'),
    amount: header.indexOf('Amount'),
    type: header.indexOf('Type'),
    notes: header.indexOf('Notes'),
    deleted: header.indexOf('Deleted'),
  };
}

function parseSheetDate_(value) {
  if (value instanceof Date) return value;
  if (!value) return null;
  const str = String(value).trim();
  const m = str.match(/^(\d{4})-(\d{2})-(\d{2})/); // what this form and the app both write
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

function validatePayload_(payload) {
  const date = String(payload.date || '').trim();
  const description = String(payload.description || '').trim();
  const amount = parseFloat(payload.amount);
  const type = String(payload.type || '').trim();
  const category = String(payload.category || '').trim() || 'Other';
  const account = String(payload.account || '').trim() || 'Primary';
  const notes = String(payload.notes || '').trim();

  if (!date) throw new Error('Date is required.');
  if (!description) throw new Error('Description is required.');
  if (!amount || amount <= 0 || isNaN(amount)) throw new Error('Amount must be a positive number.');
  if (type !== 'Income' && type !== 'Expense') throw new Error('Type must be Income or Expense.');

  return { date, description, amount, type, category, account, notes };
}

/** Populates the Category/Account dropdowns from whatever values already
 * exist in the sheet, so this form never drifts out of sync with the app's
 * own category/account list without needing to hardcode or update it here. */
function getFormOptions() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();
  const header = data[0];
  const catIdx = header.indexOf('Category');
  const acctIdx = header.indexOf('Account');

  const categories = new Set();
  const accounts = new Set();
  for (let i = 1; i < data.length; i++) {
    const cat = String(data[i][catIdx] || '').trim();
    const acct = String(data[i][acctIdx] || '').trim();
    if (cat) categories.add(cat);
    if (acct) accounts.add(acct);
  }

  return {
    categories: Array.from(categories).sort(),
    accounts: Array.from(accounts).sort(),
  };
}

/** This month's Income/Expenses/Net (deleted rows excluded), plus the most
 * recent transactions across all time, each carrying its sheet row number so
 * the client can ask to edit one. Not a dashboard - no charts - just enough
 * to sanity check "did that last entry go through" and fix typos on the go. */
function getSummary() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();
  const header = data.shift();
  const idx = {
    date: header.indexOf('Date'),
    description: header.indexOf('Description'),
    category: header.indexOf('Category'),
    amount: header.indexOf('Amount'),
    type: header.indexOf('Type'),
    deleted: header.indexOf('Deleted'),
  };

  const now = new Date();
  const curYear = now.getFullYear();
  const curMonth = now.getMonth();

  let income = 0;
  let expenses = 0;
  const rows = [];

  data.forEach((row, i) => {
    const deletedVal = String(row[idx.deleted] || '').toUpperCase();
    if (deletedVal === 'TRUE' || deletedVal === 'YES' || deletedVal === '1') return;

    const date = parseSheetDate_(row[idx.date]);
    if (!date) return;
    const amount = parseFloat(row[idx.amount]);
    if (!amount || isNaN(amount)) return;
    const type = String(row[idx.type] || '').trim();

    if (date.getFullYear() === curYear && date.getMonth() === curMonth) {
      if (type === 'Income') income += amount;
      else if (type === 'Expense') expenses += amount;
    }

    rows.push({
      sortKey: date.getTime(),
      rowNumber: i + 2, // +1 for the header row this loop skipped, +1 for 1-indexing
      date: Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd'),
      description: String(row[idx.description] || ''),
      category: String(row[idx.category] || ''),
      amount: amount,
      type: type,
    });
  });

  rows.sort((a, b) => b.sortKey - a.sortKey);
  const recent = rows.slice(0, 8).map(({ sortKey, ...rest }) => rest);

  return {
    income: income,
    expenses: expenses,
    net: income - expenses,
    recent: recent,
  };
}

function submitTransaction(payload) {
  const v = validatePayload_(payload);
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  sheet.appendRow([
    '',                   // Transaction ID - auto-assigned by the app on its next sync
    v.date,                // "YYYY-MM-DD"
    v.description,
    v.category,
    v.account,
    v.amount.toFixed(2),
    v.type,
    '',                   // Month - filled in by the app on its next sync
    v.notes,
    '',                   // Deleted
  ]);
  return { ok: true };
}

/** Full field values for one row, keyed by its sheet row number, to pre-fill
 * the form when the user taps "Edit" on a Recent item. */
function getTransactionByRow(rowNumber) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  if (!rowNumber || rowNumber < 2 || rowNumber > sheet.getLastRow()) {
    throw new Error('That transaction no longer exists at that row - refresh and try again.');
  }
  const idx = headerIndex_(sheet);
  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getValues()[0];
  const date = parseSheetDate_(row[idx.date]);

  return {
    rowNumber: rowNumber,
    date: date ? Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd') : '',
    description: String(row[idx.description] || ''),
    category: String(row[idx.category] || ''),
    account: String(row[idx.account] || ''),
    amount: row[idx.amount],
    type: String(row[idx.type] || ''),
    notes: String(row[idx.notes] || ''),
  };
}

function updateTransaction(rowNumber, payload) {
  if (!rowNumber || rowNumber < 2) throw new Error('Invalid row.');
  const v = validatePayload_(payload);

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  if (rowNumber > sheet.getLastRow()) {
    throw new Error('That transaction no longer exists at that row - refresh and try again.');
  }
  const idx = headerIndex_(sheet);

  // Transaction ID, Month and Deleted are intentionally left alone - see the
  // file header comment on why the ID in particular must not change here.
  sheet.getRange(rowNumber, idx.date + 1).setValue(v.date);
  sheet.getRange(rowNumber, idx.description + 1).setValue(v.description);
  sheet.getRange(rowNumber, idx.category + 1).setValue(v.category);
  sheet.getRange(rowNumber, idx.account + 1).setValue(v.account);
  sheet.getRange(rowNumber, idx.amount + 1).setValue(v.amount.toFixed(2));
  sheet.getRange(rowNumber, idx.type + 1).setValue(v.type);
  sheet.getRange(rowNumber, idx.notes + 1).setValue(v.notes);

  return { ok: true };
}
