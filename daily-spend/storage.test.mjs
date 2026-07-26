import assert from "node:assert/strict";
import test from "node:test";
import storageApi from "./storage.js";

const {
  STORAGE_KEY,
  ExpenseNotFoundError,
  ExpenseValidationError,
  StorageWriteBlockedError,
  addExpense,
  aggregateExpenses,
  createEmptyState,
  deleteExpense,
  formatLocalDate,
  getCategoryTotals,
  getDailyTotal,
  getExpensesForLocalDate,
  getMonthlyRegretTotal,
  getMonthlyTotal,
  getNecessityTotals,
  getTodayExpenses,
  loadState,
  parseAmountToSen,
  updateExpense
} = storageApi;

function createMemoryStorage(
  initialValue = null,
  { failOnGet = false, failOnSet = false } = {}
) {
  const state = {
    value: initialValue,
    getCalls: 0,
    setCalls: 0,
    lastKey: null
  };

  const storage = {
    getItem(key) {
      state.getCalls += 1;
      state.lastKey = key;
      if (failOnGet) {
        throw new Error("storage read failed");
      }
      return state.value;
    },
    setItem(key, value) {
      state.setCalls += 1;
      state.lastKey = key;
      if (failOnSet) {
        throw new Error("quota exceeded");
      }
      state.value = value;
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
    category: "dining",
    necessity: "needed",
    note: "",
    ...overrides
  };
}

function add(
  storage,
  id,
  now,
  overrides = {}
) {
  return addExpense(expenseInput(overrides), storage, { id, now });
}

test("loads an empty state without writing", () => {
  const { state, storage } = createMemoryStorage();

  const result = loadState(storage);

  assert.equal(result.status, "empty");
  assert.equal(result.canWrite, true);
  assert.deepEqual(result.state, createEmptyState());
  assert.equal(state.getCalls, 1);
  assert.equal(state.setCalls, 0);
  assert.equal(state.lastKey, STORAGE_KEY);
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

test("rejects empty, zero, negative, malformed, over-precise, and unsafe amounts", () => {
  const invalidValues = [
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
  ];

  for (const value of invalidValues) {
    assert.throws(
      () => parseAmountToSen(value),
      ExpenseValidationError,
      `expected ${JSON.stringify(value)} to be rejected`
    );
  }

  assert.throws(
    () => parseAmountToSen(12.34),
    ExpenseValidationError
  );
});

test("adds, reloads, and normalizes a one-line note", () => {
  const { state: memory, storage } = createMemoryStorage();
  const now = localDate(2026, 6, 26, 9, 15);

  const added = add(storage, "expense-1", now, {
    amount: "18.90",
    category: "groceries",
    necessity: "hesitated",
    note: "  帰宅前\nに購入  "
  });
  const loaded = loadState(storage);

  assert.equal(added.expenses.length, 1);
  assert.deepEqual(added.expenses[0], {
    id: "expense-1",
    amountSen: 1890,
    category: "groceries",
    necessity: "hesitated",
    note: "帰宅前 に購入",
    recordedAt: now.toISOString(),
    recordedLocalDate: "2026-07-26",
    updatedAt: now.toISOString()
  });
  assert.equal(loaded.status, "ok");
  assert.deepEqual(loaded.state, added);
  assert.equal(memory.setCalls, 1);
  assert.equal(memory.lastKey, STORAGE_KEY);
});

test("requires an explicit category and necessity", () => {
  const { state, storage } = createMemoryStorage();
  const now = localDate(2026, 6, 26);

  assert.throws(
    () =>
      addExpense(
        expenseInput({ category: null }),
        storage,
        { id: "missing-category", now }
      ),
    (error) =>
      error instanceof ExpenseValidationError &&
      error.code === "category_required"
  );
  assert.throws(
    () =>
      addExpense(
        expenseInput({ necessity: null }),
        storage,
        { id: "missing-necessity", now }
      ),
    (error) =>
      error instanceof ExpenseValidationError &&
      error.code === "necessity_required"
  );
  assert.equal(state.setCalls, 0);
});

test("reports missing fields in the visible input order", () => {
  const { state, storage } = createMemoryStorage();
  const now = localDate(2026, 6, 26);

  assert.throws(
    () =>
      addExpense(
        {
          amount: "",
          category: null,
          necessity: null,
          note: ""
        },
        storage,
        { id: "missing-all", now }
      ),
    (error) =>
      error instanceof ExpenseValidationError &&
      error.code === "amount_required"
  );
  assert.throws(
    () =>
      addExpense(
        {
          amount: "1.00",
          category: null,
          necessity: null,
          note: ""
        },
        storage,
        { id: "missing-selections", now }
      ),
    (error) =>
      error instanceof ExpenseValidationError &&
      error.code === "category_required"
  );
  assert.equal(state.setCalls, 0);
});

test("updates editable fields while preserving the original timestamp and local date", () => {
  const { storage } = createMemoryStorage();
  const recordedAt = localDate(2026, 6, 26, 23, 58);
  const updatedAt = localDate(2026, 6, 27, 0, 2);

  add(storage, "expense-1", recordedAt);
  add(storage, "expense-2", localDate(2026, 6, 26, 20));
  const before = loadState(storage).state;

  const updated = updateExpense(
    "expense-1",
    expenseInput({
      amount: "45.67",
      category: "medical",
      necessity: "unnecessary",
      note: "updated"
    }),
    storage,
    { now: updatedAt }
  );

  const first = updated.expenses.find(
    (expense) => expense.id === "expense-1"
  );
  assert.equal(first.amountSen, 4567);
  assert.equal(first.category, "medical");
  assert.equal(first.necessity, "unnecessary");
  assert.equal(first.note, "updated");
  assert.equal(first.recordedAt, recordedAt.toISOString());
  assert.equal(first.recordedLocalDate, "2026-07-26");
  assert.equal(first.updatedAt, updatedAt.toISOString());
  assert.deepEqual(updated.expenses[1], before.expenses[1]);
});

test("deletes one expense and rejects unknown ids", () => {
  const { storage } = createMemoryStorage();
  const now = localDate(2026, 6, 26);

  add(storage, "expense-1", now);
  add(storage, "expense-2", now);
  const afterDelete = deleteExpense("expense-1", storage);

  assert.deepEqual(
    afterDelete.expenses.map((expense) => expense.id),
    ["expense-2"]
  );
  assert.throws(
    () => deleteExpense("missing", storage),
    ExpenseNotFoundError
  );
});

test("rejects duplicate ids without changing stored state", () => {
  const { state: memory, storage } = createMemoryStorage();
  const now = localDate(2026, 6, 26);

  const first = add(storage, "same-id", now);

  assert.throws(
    () => add(storage, "same-id", now),
    (error) =>
      error instanceof ExpenseValidationError &&
      error.code === "id_duplicate"
  );
  assert.equal(memory.setCalls, 1);
  assert.deepEqual(loadState(storage).state, first);
});

test("lists only the selected local day, newest first", () => {
  const { storage } = createMemoryStorage();
  add(storage, "yesterday", localDate(2026, 6, 25, 23, 59));
  add(storage, "morning", localDate(2026, 6, 26, 8));
  add(storage, "evening", localDate(2026, 6, 26, 20));
  const state = loadState(storage).state;

  assert.deepEqual(
    getTodayExpenses(state, localDate(2026, 6, 26))
      .map((expense) => expense.id),
    ["evening", "morning"]
  );
  assert.deepEqual(
    getExpensesForLocalDate(state, "2026-07-25")
      .map((expense) => expense.id),
    ["yesterday"]
  );
});

test("aggregates daily, monthly, category, and necessity totals across a month boundary", () => {
  const { storage } = createMemoryStorage();

  add(storage, "june", localDate(2026, 5, 30), {
    amount: "1.00",
    category: "other",
    necessity: "unnecessary"
  });
  add(storage, "july-needed", localDate(2026, 6, 1), {
    amount: "10.25",
    category: "groceries",
    necessity: "needed"
  });
  add(storage, "july-hesitated", localDate(2026, 6, 26), {
    amount: "20.50",
    category: "dining",
    necessity: "hesitated"
  });
  add(storage, "july-unnecessary", localDate(2026, 6, 26), {
    amount: "3.75",
    category: "shopping",
    necessity: "unnecessary"
  });
  add(storage, "august", localDate(2026, 7, 1), {
    amount: "100.00",
    category: "medical",
    necessity: "hesitated"
  });

  const state = loadState(storage).state;
  assert.equal(getDailyTotal(state, "2026-07-26"), 2425);
  assert.equal(getMonthlyTotal(state, "2026-07"), 3450);
  assert.equal(getMonthlyRegretTotal(state, "2026-07"), 2425);

  assert.deepEqual(
    getCategoryTotals(state, { localMonth: "2026-07" }),
    {
      dining: 2050,
      groceries: 1025,
      shopping: 375,
      health: 0,
      medical: 0,
      other: 0
    }
  );
  assert.deepEqual(
    getNecessityTotals(state, { localMonth: "2026-07" }),
    {
      needed: 1025,
      hesitated: 2050,
      unnecessary: 375
    }
  );
  assert.deepEqual(
    aggregateExpenses(state, { localDate: "2026-06-30" }),
    {
      totalSen: 100,
      byCategory: {
        dining: 0,
        groceries: 0,
        shopping: 0,
        health: 0,
        medical: 0,
        other: 100
      },
      byNecessity: {
        needed: 0,
        hesitated: 0,
        unnecessary: 100
      }
    }
  );
});

test("formats dates from local calendar components", () => {
  assert.equal(
    formatLocalDate(localDate(2026, 11, 31, 23, 59)),
    "2026-12-31"
  );
  assert.equal(
    formatLocalDate(localDate(2027, 0, 1, 0, 0)),
    "2027-01-01"
  );
});

test("blocks writes and preserves invalid JSON", () => {
  const original = "{not-json";
  const { state, storage } = createMemoryStorage(original);

  const result = loadState(storage);

  assert.equal(result.status, "invalid");
  assert.equal(result.errorCode, "invalid_json");
  assert.equal(result.canWrite, false);
  assert.throws(
    () => add(storage, "blocked", localDate(2026, 6, 26)),
    StorageWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("blocks writes and preserves a future schema version", () => {
  const original = JSON.stringify({
    schemaVersion: 2,
    expenses: [],
    futureField: true
  });
  const { state, storage } = createMemoryStorage(original);

  const result = loadState(storage);

  assert.equal(result.status, "unsupported_version");
  assert.equal(result.errorCode, "unsupported_future_version");
  assert.equal(result.canWrite, false);
  assert.throws(
    () => add(storage, "blocked", localDate(2026, 6, 26)),
    StorageWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("blocks writes and preserves malformed version 1 data", () => {
  const malformedStates = [
    {
      schemaVersion: 1,
      expenses: [{ id: "incomplete" }]
    },
    {
      schemaVersion: 1,
      expenses: [
        {
          id: "duplicate",
          amountSen: 100,
          category: "other",
          necessity: "needed",
          note: "",
          recordedAt: "2026-07-26T00:00:00.000Z",
          recordedLocalDate: "2026-07-26",
          updatedAt: "2026-07-26T00:00:00.000Z"
        },
        {
          id: "duplicate",
          amountSen: 200,
          category: "dining",
          necessity: "hesitated",
          note: "",
          recordedAt: "2026-07-26T01:00:00.000Z",
          recordedLocalDate: "2026-07-26",
          updatedAt: "2026-07-26T01:00:00.000Z"
        }
      ]
    }
  ];

  for (const malformed of malformedStates) {
    const original = JSON.stringify(malformed);
    const { state, storage } = createMemoryStorage(original);
    const result = loadState(storage);

    assert.equal(result.status, "invalid");
    assert.equal(result.errorCode, "invalid_state");
    assert.equal(result.canWrite, false);
    assert.throws(
      () => add(storage, "blocked", localDate(2026, 6, 26)),
      StorageWriteBlockedError
    );
    assert.equal(state.setCalls, 0);
    assert.equal(state.value, original);
  }
});

test("reports unavailable storage and blocks mutations after read failure", () => {
  const { state, storage } = createMemoryStorage(null, {
    failOnGet: true
  });

  const result = loadState(storage);

  assert.equal(result.status, "unavailable");
  assert.equal(result.errorCode, "storage_read_failed");
  assert.equal(result.canWrite, false);
  assert.throws(
    () => add(storage, "blocked", localDate(2026, 6, 26)),
    StorageWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
});

test("does not change stored data when a write fails", () => {
  const original = JSON.stringify(createEmptyState());
  const { state, storage } = createMemoryStorage(original, {
    failOnSet: true
  });

  assert.throws(
    () => add(storage, "not-saved", localDate(2026, 6, 26)),
    /quota exceeded/
  );
  assert.equal(state.value, original);
  assert.equal(state.setCalls, 1);
  assert.deepEqual(loadState(storage).state, createEmptyState());
});
