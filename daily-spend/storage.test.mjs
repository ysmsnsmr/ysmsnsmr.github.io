import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import "./storage.js";

const storageApi = globalThis.DailySpendStorage;

const {
  APP_ID,
  STORAGE_KEY,
  V1_BACKUP_KEY,
  PRE_IMPORT_BACKUP_KEY,
  V2_ROLLBACK_BACKUP_KEY,
  SCHEMA_VERSION,
  EXPORT_VERSION,
  CATEGORY_IDS,
  ExpenseNotFoundError,
  ExpenseValidationError,
  ImportValidationError,
  StorageWriteBlockedError,
  addExpense,
  createEmptyState,
  deleteExpense,
  diagnoseRawValue,
  diagnoseStoredData,
  formatLocalDate,
  getCategoryTotals,
  getDailyTotal,
  getMonthlyRegretTotal,
  getMonthlyTotal,
  getRawStoredValue,
  getRecentPastExpenses,
  getTodayExpenses,
  importState,
  loadState,
  parseAmountToSen,
  parseImportText,
  restoreExpense,
  rollbackToV1Backup,
  serializeExport,
  updateExpense
} = storageApi;

const v1FixtureRaw = fs.readFileSync(
  new URL("./fixtures/state-v1-valid.json", import.meta.url),
  "utf8"
);
const v1Fixture = JSON.parse(v1FixtureRaw);

function createMemoryStorage(
  initialValue = null,
  { failOnGet = false, failOnSet = null } = {}
) {
  const values = new Map();
  if (initialValue !== null) {
    values.set(STORAGE_KEY, initialValue);
  }
  const state = {
    getCalls: [],
    setCalls: [],
    values
  };
  const storage = {
    getItem(key) {
      state.getCalls.push(key);
      if (failOnGet) {
        throw new Error("storage read failed");
      }
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      state.setCalls.push({ key, value });
      if (
        failOnSet === true ||
        (typeof failOnSet === "function" && failOnSet(key, value))
      ) {
        throw new Error("quota exceeded");
      }
      values.set(key, value);
    }
  };
  return { state, storage };
}

function localDate(year, monthIndex, day, hour = 12, minute = 0) {
  return new Date(year, monthIndex, day, hour, minute, 0, 0);
}

function expenseInput(overrides = {}) {
  return {
    amount: "12.34",
    categoryId: "daily-spend:dining",
    necessity: "needed",
    note: "",
    ...overrides
  };
}

function add(storage, id, now, overrides = {}) {
  return addExpense(expenseInput(overrides), storage, { id, now });
}

function validV2Expense(overrides = {}) {
  return {
    id: "expense-1",
    amountSen: 1234,
    categoryId: "daily-spend:dining",
    necessity: "needed",
    note: "",
    recordedAt: "2026-08-01T04:00:00.000Z",
    recordedLocalDate: "2026-08-01",
    updatedAt: "2026-08-01T04:00:00.000Z",
    ...overrides
  };
}

function v2State(expenses = []) {
  return { schemaVersion: 2, expenses };
}

test("loads an empty v2 state without writing", () => {
  const { state, storage } = createMemoryStorage();
  const result = loadState(storage);

  assert.equal(result.status, "empty");
  assert.equal(result.canWrite, true);
  assert.deepEqual(result.state, createEmptyState());
  assert.equal(result.diagnosis.status, "empty");
  assert.equal(state.setCalls.length, 0);
});

test("parses valid MYR strings into integer sen", () => {
  assert.equal(parseAmountToSen("1"), 100);
  assert.equal(parseAmountToSen("1.2"), 120);
  assert.equal(parseAmountToSen("1.20"), 120);
  assert.equal(parseAmountToSen(" 001.05 "), 105);
  assert.equal(
    parseAmountToSen("90071992547409.91"),
    Number.MAX_SAFE_INTEGER
  );
});

test("rejects empty, nonpositive, malformed, precise, and unsafe amounts", () => {
  for (const value of [
    "",
    " ",
    "0",
    "0.00",
    "-1",
    "+1",
    ".50",
    "1.",
    "1,000",
    "abc",
    "1.234",
    "90071992547409.92"
  ]) {
    assert.throws(() => parseAmountToSen(value), ExpenseValidationError);
  }
});

test("adds and reloads a v2 expense with a stable category ID", () => {
  const { storage } = createMemoryStorage();
  const now = localDate(2026, 7, 4, 9, 15);
  const added = add(storage, "expense-1", now, {
    amount: "18.90",
    categoryId: "daily-spend:groceries",
    necessity: "hesitated",
    note: "  帰宅前\nに購入  "
  });

  assert.equal(added.schemaVersion, 2);
  assert.deepEqual(added.expenses[0], {
    id: "expense-1",
    amountSen: 1890,
    categoryId: "daily-spend:groceries",
    necessity: "hesitated",
    note: "帰宅前 に購入",
    recordedAt: now.toISOString(),
    recordedLocalDate: "2026-08-04",
    updatedAt: now.toISOString()
  });
  assert.deepEqual(loadState(storage).state, added);
  assert.equal("category" in added.expenses[0], false);
});

test("category definitions are app-owned stable IDs", () => {
  assert.deepEqual(CATEGORY_IDS, [
    "daily-spend:dining",
    "daily-spend:groceries",
    "daily-spend:shopping",
    "daily-spend:health",
    "daily-spend:medical",
    "daily-spend:other"
  ]);
  assert.ok(CATEGORY_IDS.every((id) => id.startsWith("daily-spend:")));
});

test("requires amount, category ID, and necessity in visible order", () => {
  const { state, storage } = createMemoryStorage();
  const now = localDate(2026, 7, 4);
  assert.throws(
    () =>
      addExpense(
        { amount: "", categoryId: null, necessity: null, note: "" },
        storage,
        { id: "missing", now }
      ),
    (error) =>
      error instanceof ExpenseValidationError &&
      error.code === "amount_required"
  );
  assert.throws(
    () =>
      addExpense(
        { amount: "1", categoryId: null, necessity: null, note: "" },
        storage,
        { id: "missing", now }
      ),
    (error) =>
      error instanceof ExpenseValidationError &&
      error.code === "category_required"
  );
  assert.equal(state.setCalls.length, 0);
});

test("updates editable fields while preserving original date and timestamp", () => {
  const { storage } = createMemoryStorage();
  const recordedAt = localDate(2026, 7, 4, 23, 58);
  const updatedAt = localDate(2026, 7, 5, 0, 2);
  add(storage, "expense-1", recordedAt);
  add(storage, "expense-2", localDate(2026, 7, 4, 20));
  const before = loadState(storage).state;

  const updated = updateExpense(
    "expense-1",
    expenseInput({
      amount: "45.67",
      categoryId: "daily-spend:medical",
      necessity: "unnecessary",
      note: "updated"
    }),
    storage,
    { now: updatedAt }
  );
  const first = updated.expenses.find((item) => item.id === "expense-1");
  assert.equal(first.categoryId, "daily-spend:medical");
  assert.equal(first.recordedAt, recordedAt.toISOString());
  assert.equal(first.recordedLocalDate, "2026-08-04");
  assert.equal(first.updatedAt, updatedAt.toISOString());
  assert.deepEqual(updated.expenses[1], before.expenses[1]);
});

test("deletes and restores the exact expense for Undo", () => {
  const { storage } = createMemoryStorage();
  const now = localDate(2026, 7, 4);
  const added = add(storage, "expense-1", now);
  const deletedExpense = { ...added.expenses[0] };
  const afterDelete = deleteExpense("expense-1", storage);
  const afterRestore = restoreExpense(deletedExpense, storage);

  assert.equal(afterDelete.expenses.length, 0);
  assert.deepEqual(afterRestore.expenses, [deletedExpense]);
  assert.throws(() => restoreExpense(deletedExpense, storage), (error) =>
    error instanceof ExpenseValidationError && error.code === "id_duplicate"
  );
  assert.throws(() => deleteExpense("missing", storage), ExpenseNotFoundError);
});

test("returns only the previous 30 local dates for history", () => {
  const { storage } = createMemoryStorage();
  add(storage, "too-old", localDate(2026, 6, 4));
  add(storage, "oldest", localDate(2026, 6, 5));
  add(storage, "yesterday", localDate(2026, 7, 3));
  add(storage, "today", localDate(2026, 7, 4));
  const state = loadState(storage).state;

  assert.deepEqual(
    getRecentPastExpenses(state, localDate(2026, 7, 4), 30).map(
      (expense) => expense.id
    ),
    ["yesterday", "oldest"]
  );
  assert.deepEqual(
    getTodayExpenses(state, localDate(2026, 7, 4)).map(
      (expense) => expense.id
    ),
    ["today"]
  );
});

test("aggregates v2 category IDs across a month boundary", () => {
  const { storage } = createMemoryStorage();
  add(storage, "july", localDate(2026, 6, 31), {
    amount: "1.00",
    categoryId: "daily-spend:other",
    necessity: "unnecessary"
  });
  add(storage, "needed", localDate(2026, 7, 1), {
    amount: "10.25",
    categoryId: "daily-spend:groceries"
  });
  add(storage, "hesitated", localDate(2026, 7, 4), {
    amount: "20.50",
    categoryId: "daily-spend:dining",
    necessity: "hesitated"
  });
  const state = loadState(storage).state;

  assert.equal(getDailyTotal(state, "2026-08-04"), 2050);
  assert.equal(getMonthlyTotal(state, "2026-08"), 3075);
  assert.equal(getMonthlyRegretTotal(state, "2026-08"), 2050);
  assert.equal(
    getCategoryTotals(state, { localMonth: "2026-08" })[
      "daily-spend:dining"
    ],
    2050
  );
});

test("migrates the canonical v1 fixture only after exact backup", () => {
  const { state, storage } = createMemoryStorage(v1FixtureRaw);
  const result = loadState(storage);

  assert.equal(result.status, "migrated");
  assert.equal(result.migratedFromVersion, 1);
  assert.equal(result.state.schemaVersion, 2);
  assert.deepEqual(
    result.state.expenses.map((expense) => expense.categoryId),
    ["daily-spend:dining", "daily-spend:groceries"]
  );
  assert.equal(state.values.get(V1_BACKUP_KEY), v1FixtureRaw);
  assert.equal(
    JSON.parse(state.values.get(STORAGE_KEY)).schemaVersion,
    SCHEMA_VERSION
  );
  assert.deepEqual(
    state.setCalls.map((call) => call.key),
    [V1_BACKUP_KEY, STORAGE_KEY]
  );
});

test("blocks migration when immutable v1 backup conflicts", () => {
  const { state, storage } = createMemoryStorage(v1FixtureRaw);
  state.values.set(V1_BACKUP_KEY, "different-v1-copy");
  const result = loadState(storage);

  assert.equal(result.status, "migration_failed");
  assert.equal(result.errorCode, "backup_conflict");
  assert.equal(result.canWrite, false);
  assert.equal(state.values.get(STORAGE_KEY), v1FixtureRaw);
  assert.equal(state.setCalls.length, 0);
});

test("leaves v1 active when pre-migration backup cannot be written", () => {
  const { state, storage } = createMemoryStorage(v1FixtureRaw, {
    failOnSet: (key) => key === V1_BACKUP_KEY
  });
  const result = loadState(storage);

  assert.equal(result.status, "migration_failed");
  assert.equal(result.canWrite, false);
  assert.equal(state.values.get(STORAGE_KEY), v1FixtureRaw);
  assert.equal(state.values.has(V1_BACKUP_KEY), false);
});

test("rollback copies current v2 and restores the exact v1 fixture", () => {
  const activeV2 = JSON.stringify(
    v2State([validV2Expense({ id: "new-v2" })])
  );
  const { state, storage } = createMemoryStorage(activeV2);
  state.values.set(V1_BACKUP_KEY, v1FixtureRaw);

  const restored = rollbackToV1Backup(storage);

  assert.deepEqual(restored, v1Fixture);
  assert.equal(state.values.get(STORAGE_KEY), v1FixtureRaw);
  assert.equal(state.values.get(V2_ROLLBACK_BACKUP_KEY), activeV2);
});

test("rollback stops without changing active state when v1 backup is missing", () => {
  const activeV2 = JSON.stringify(v2State([validV2Expense()]));
  const { state, storage } = createMemoryStorage(activeV2);
  assert.throws(() => rollbackToV1Backup(storage), (error) =>
    error instanceof StorageWriteBlockedError &&
    error.code === "v1_backup_missing"
  );
  assert.equal(state.values.get(STORAGE_KEY), activeV2);
  assert.equal(state.values.has(V2_ROLLBACK_BACKUP_KEY), false);
});

test("creates a versioned JSON export envelope", () => {
  const state = v2State([validV2Expense()]);
  const exportedAt = new Date("2026-08-04T01:02:03.000Z");
  const parsed = JSON.parse(serializeExport(state, exportedAt));

  assert.equal(parsed.appId, APP_ID);
  assert.equal(parsed.exportVersion, EXPORT_VERSION);
  assert.equal(parsed.exportedAt, exportedAt.toISOString());
  assert.deepEqual(parsed.state, state);
});

test("imports a versioned export into empty storage", () => {
  const incoming = v2State([validV2Expense()]);
  const text = serializeExport(incoming, new Date("2026-08-04T00:00:00Z"));
  const { state, storage } = createMemoryStorage();
  const result = importState(text, storage);

  assert.equal(result.addedCount, 1);
  assert.equal(result.duplicateCount, 0);
  assert.deepEqual(result.state, incoming);
  assert.equal(state.values.has(PRE_IMPORT_BACKUP_KEY), false);
});

test("imports raw v1 by converting categories to v2 IDs", () => {
  const { storage } = createMemoryStorage();
  const result = importState(v1FixtureRaw, storage);

  assert.equal(result.sourceSchemaVersion, 1);
  assert.equal(result.state.schemaVersion, 2);
  assert.equal(
    result.state.expenses[0].categoryId,
    "daily-spend:dining"
  );
});

test("merges new records and deduplicates exact IDs on import", () => {
  const current = v2State([validV2Expense({ id: "same" })]);
  const incoming = v2State([
    validV2Expense({ id: "same" }),
    validV2Expense({ id: "new", amountSen: 999 })
  ]);
  const currentRaw = JSON.stringify(current);
  const { state, storage } = createMemoryStorage(currentRaw);
  const result = importState(JSON.stringify(incoming), storage);

  assert.equal(result.addedCount, 1);
  assert.equal(result.duplicateCount, 1);
  assert.equal(result.state.expenses.length, 2);
  assert.equal(state.values.get(PRE_IMPORT_BACKUP_KEY), currentRaw);
});

test("rejects conflicting IDs before writing state or import backup", () => {
  const current = v2State([validV2Expense({ id: "same" })]);
  const incoming = v2State([
    validV2Expense({ id: "same", amountSen: 999 })
  ]);
  const currentRaw = JSON.stringify(current);
  const { state, storage } = createMemoryStorage(currentRaw);

  assert.throws(
    () => importState(JSON.stringify(incoming), storage),
    (error) =>
      error instanceof ImportValidationError &&
      error.code === "import_id_conflict"
  );
  assert.equal(state.values.get(STORAGE_KEY), currentRaw);
  assert.equal(state.values.has(PRE_IMPORT_BACKUP_KEY), false);
  assert.equal(state.setCalls.length, 0);
});

test("backs up corrupt raw state before replacing it with a valid import", () => {
  const corruptRaw = "{not-json";
  const incoming = JSON.stringify(v2State([validV2Expense()]));
  const { state, storage } = createMemoryStorage(corruptRaw);
  const result = importState(incoming, storage);

  assert.equal(result.addedCount, 1);
  assert.equal(state.values.get(PRE_IMPORT_BACKUP_KEY), corruptRaw);
  assert.deepEqual(JSON.parse(state.values.get(STORAGE_KEY)), result.state);
});

test("invalid import changes neither active state nor backup", () => {
  const currentRaw = JSON.stringify(v2State([validV2Expense()]));
  const { state, storage } = createMemoryStorage(currentRaw);
  assert.throws(() => importState("{bad", storage), ImportValidationError);
  assert.equal(state.values.get(STORAGE_KEY), currentRaw);
  assert.equal(state.values.has(PRE_IMPORT_BACKUP_KEY), false);
  assert.equal(state.setCalls.length, 0);
});

test("raw export returns the exact stored string", () => {
  const raw = "{\n  \"schemaVersion\": 2,\n  \"expenses\": []\n}";
  const { storage } = createMemoryStorage(raw);
  assert.equal(getRawStoredValue(storage), raw);
});

test("diagnoses invalid JSON without changing it", () => {
  const raw = "{not-json";
  const { state, storage } = createMemoryStorage(raw);
  const diagnosis = diagnoseStoredData(storage);
  const loaded = loadState(storage);

  assert.equal(diagnosis.status, "invalid_json");
  assert.equal(diagnosis.issues[0].path, "$");
  assert.equal(loaded.status, "invalid");
  assert.equal(loaded.rawValue, raw);
  assert.equal(state.setCalls.length, 0);
});

test("diagnoses one corrupt expense while counting valid siblings", () => {
  const raw = JSON.stringify(
    v2State([
      validV2Expense({ id: "valid" }),
      validV2Expense({
        id: "broken",
        amountSen: -1,
        categoryId: "bank-statement:Dining"
      })
    ])
  );
  const diagnosis = diagnoseRawValue(raw);

  assert.equal(diagnosis.status, "invalid");
  assert.equal(diagnosis.totalExpenseCount, 2);
  assert.equal(diagnosis.validExpenseCount, 1);
  assert.equal(diagnosis.invalidExpenseCount, 1);
  assert.deepEqual(
    diagnosis.issues.map((entry) => entry.path),
    ["expenses[1].amountSen", "expenses[1].categoryId"]
  );
  assert.ok(diagnosis.issues.every((entry) => entry.expenseId === "broken"));
});

test("blocks all writes when one v2 expense is corrupt", () => {
  const raw = JSON.stringify(
    v2State([
      validV2Expense({ id: "valid" }),
      validV2Expense({ id: "broken", recordedLocalDate: "2026-02-30" })
    ])
  );
  const { state, storage } = createMemoryStorage(raw);
  const result = loadState(storage);

  assert.equal(result.status, "invalid");
  assert.equal(result.canWrite, false);
  assert.equal(result.diagnosis.invalidExpenseCount, 1);
  assert.throws(
    () => add(storage, "blocked", localDate(2026, 7, 4)),
    StorageWriteBlockedError
  );
  assert.equal(state.values.get(STORAGE_KEY), raw);
  assert.equal(state.setCalls.length, 0);
});

test("diagnoses duplicate expense IDs", () => {
  const raw = JSON.stringify(
    v2State([
      validV2Expense({ id: "duplicate" }),
      validV2Expense({ id: "duplicate", amountSen: 200 })
    ])
  );
  const diagnosis = diagnoseRawValue(raw);
  assert.equal(diagnosis.invalidExpenseCount, 1);
  assert.equal(
    diagnosis.issues.some((entry) => entry.code === "duplicate_id"),
    true
  );
});

test("preserves and blocks a future schema version", () => {
  const raw = JSON.stringify({ schemaVersion: 3, expenses: [] });
  const { state, storage } = createMemoryStorage(raw);
  const result = loadState(storage);
  assert.equal(result.status, "unsupported_version");
  assert.equal(result.diagnosis.status, "future_version");
  assert.equal(state.setCalls.length, 0);
  assert.equal(state.values.get(STORAGE_KEY), raw);
});

test("reports unavailable storage after read failure", () => {
  const { state, storage } = createMemoryStorage(null, {
    failOnGet: true
  });
  const result = loadState(storage);
  assert.equal(result.status, "unavailable");
  assert.equal(result.canWrite, false);
  assert.equal(state.setCalls.length, 0);
});

test("does not change active data when a normal write fails", () => {
  const raw = JSON.stringify(createEmptyState());
  const { state, storage } = createMemoryStorage(raw, {
    failOnSet: (key) => key === STORAGE_KEY
  });
  assert.throws(
    () => add(storage, "not-saved", localDate(2026, 7, 4)),
    /quota exceeded/
  );
  assert.equal(state.values.get(STORAGE_KEY), raw);
});

test("formats local dates without UTC conversion", () => {
  assert.equal(
    formatLocalDate(localDate(2026, 11, 31, 23, 59)),
    "2026-12-31"
  );
  assert.equal(
    formatLocalDate(localDate(2027, 0, 1, 0, 0)),
    "2027-01-01"
  );
});

test("parseImportText rejects another app and future export version", () => {
  assert.throws(
    () =>
      parseImportText(
        JSON.stringify({
          appId: "bank-statement-sorter",
          exportVersion: 1,
          state: createEmptyState()
        })
      ),
    (error) =>
      error instanceof ImportValidationError &&
      error.code === "import_wrong_app"
  );
  assert.throws(
    () =>
      parseImportText(
        JSON.stringify({
          appId: APP_ID,
          exportVersion: 2,
          state: createEmptyState()
        })
      ),
    (error) =>
      error instanceof ImportValidationError &&
      error.code === "import_future_version"
  );
});
