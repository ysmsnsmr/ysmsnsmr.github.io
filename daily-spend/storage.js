(function attachDailySpendStorage(globalObject) {
  "use strict";

  const STORAGE_KEY = "daily-spend-state";
  const SCHEMA_VERSION = 1;
  const CATEGORIES = Object.freeze([
    "dining",
    "groceries",
    "shopping",
    "health",
    "medical",
    "other"
  ]);
  const NECESSITIES = Object.freeze([
    "needed",
    "hesitated",
    "unnecessary"
  ]);
  const LOCAL_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
  const LOCAL_MONTH_PATTERN = /^\d{4}-\d{2}$/;
  const AMOUNT_PATTERN = /^\d+(?:\.\d{1,2})?$/;

  class StorageWriteBlockedError extends Error {
    constructor(code) {
      super(`Daily Spend write blocked: ${code}`);
      this.name = "StorageWriteBlockedError";
      this.code = code;
    }
  }

  class ExpenseNotFoundError extends Error {
    constructor(expenseId) {
      super(`Expense not found: ${expenseId}`);
      this.name = "ExpenseNotFoundError";
      this.expenseId = expenseId;
    }
  }

  class ExpenseValidationError extends Error {
    constructor(code) {
      super(`Daily Spend validation failed: ${code}`);
      this.name = "ExpenseValidationError";
      this.code = code;
    }
  }

  function createEmptyState() {
    return {
      schemaVersion: SCHEMA_VERSION,
      expenses: []
    };
  }

  function loadState(storage = getBrowserStorage()) {
    if (!storage) {
      return createLoadResult("unavailable", false, "storage_read_failed");
    }

    let storedValue;
    try {
      storedValue = storage.getItem(STORAGE_KEY);
    } catch {
      return createLoadResult("unavailable", false, "storage_read_failed");
    }

    if (storedValue === null) {
      return createLoadResult("empty", true, null);
    }

    let parsed;
    try {
      parsed = JSON.parse(storedValue);
    } catch {
      return createLoadResult("invalid", false, "invalid_json");
    }

    if (
      isRecord(parsed) &&
      Number.isInteger(parsed.schemaVersion) &&
      parsed.schemaVersion > SCHEMA_VERSION
    ) {
      return createLoadResult(
        "unsupported_version",
        false,
        "unsupported_future_version"
      );
    }

    if (!isValidState(parsed)) {
      return createLoadResult("invalid", false, "invalid_state");
    }

    return {
      status: "ok",
      state: cloneState(parsed),
      canWrite: true,
      errorCode: null
    };
  }

  function addExpense(
    input,
    storage = getBrowserStorage(),
    options = {}
  ) {
    const state = loadWritableState(storage);
    const normalized = normalizeExpenseInput(input);
    const now = resolveDate(options.now);
    const timestamp = now.toISOString();
    const id = options.id === undefined ? createExpenseId() : options.id;

    if (!isNonEmptyString(id)) {
      throw new ExpenseValidationError("id_invalid");
    }
    if (state.expenses.some((expense) => expense.id === id)) {
      throw new ExpenseValidationError("id_duplicate");
    }

    const nextState = {
      schemaVersion: SCHEMA_VERSION,
      expenses: [
        ...state.expenses,
        {
          id,
          amountSen: normalized.amountSen,
          category: normalized.category,
          necessity: normalized.necessity,
          note: normalized.note,
          recordedAt: timestamp,
          recordedLocalDate: formatLocalDate(now),
          updatedAt: timestamp
        }
      ]
    };

    return persistState(nextState, storage);
  }

  function updateExpense(
    expenseId,
    input,
    storage = getBrowserStorage(),
    options = {}
  ) {
    const state = loadWritableState(storage);
    const existing = findExpense(state, expenseId);
    const normalized = normalizeExpenseInput(input);
    const updatedAt = resolveDate(options.now).toISOString();
    const replacement = {
      ...existing,
      amountSen: normalized.amountSen,
      category: normalized.category,
      necessity: normalized.necessity,
      note: normalized.note,
      updatedAt
    };

    const nextState = {
      schemaVersion: SCHEMA_VERSION,
      expenses: state.expenses.map((expense) =>
        expense.id === expenseId ? replacement : expense
      )
    };

    return persistState(nextState, storage);
  }

  function deleteExpense(expenseId, storage = getBrowserStorage()) {
    const state = loadWritableState(storage);
    findExpense(state, expenseId);

    return persistState(
      {
        schemaVersion: SCHEMA_VERSION,
        expenses: state.expenses.filter(
          (expense) => expense.id !== expenseId
        )
      },
      storage
    );
  }

  function parseAmountToSen(value) {
    if (typeof value !== "string") {
      throw new ExpenseValidationError("amount_invalid");
    }

    const normalized = value.trim();
    if (normalized.length === 0) {
      throw new ExpenseValidationError("amount_required");
    }
    if (!AMOUNT_PATTERN.test(normalized)) {
      throw new ExpenseValidationError("amount_invalid");
    }

    const [ringgitPart, senPart = ""] = normalized.split(".");
    const amount =
      BigInt(ringgitPart) * 100n +
      BigInt(senPart.padEnd(2, "0"));

    if (amount <= 0n) {
      throw new ExpenseValidationError("amount_positive");
    }
    if (amount > BigInt(Number.MAX_SAFE_INTEGER)) {
      throw new ExpenseValidationError("amount_too_large");
    }

    return Number(amount);
  }

  function formatLocalDate(value = new Date()) {
    const date = resolveDate(value);
    const year = String(date.getFullYear()).padStart(4, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function formatLocalMonth(value = new Date()) {
    return formatLocalDate(value).slice(0, 7);
  }

  function getTodayExpenses(state, date = new Date()) {
    return getExpensesForLocalDate(state, formatLocalDate(date));
  }

  function getExpensesForLocalDate(state, localDate) {
    assertValidState(state);
    assertLocalDate(localDate);

    return state.expenses
      .filter((expense) => expense.recordedLocalDate === localDate)
      .sort(
        (left, right) =>
          right.recordedAt.localeCompare(left.recordedAt) ||
          right.id.localeCompare(left.id)
      )
      .map((expense) => ({ ...expense }));
  }

  function getDailyTotal(state, value = new Date()) {
    const localDate =
      typeof value === "string" ? value : formatLocalDate(value);
    return aggregateExpenses(state, { localDate }).totalSen;
  }

  function getMonthlyTotal(state, value = new Date()) {
    const localMonth =
      typeof value === "string" ? value : formatLocalMonth(value);
    return aggregateExpenses(state, { localMonth }).totalSen;
  }

  function getMonthlyRegretTotal(state, value = new Date()) {
    const localMonth =
      typeof value === "string" ? value : formatLocalMonth(value);
    const totals = aggregateExpenses(state, { localMonth }).byNecessity;
    return totals.hesitated + totals.unnecessary;
  }

  function getCategoryTotals(state, filters = {}) {
    return aggregateExpenses(state, filters).byCategory;
  }

  function getNecessityTotals(state, filters = {}) {
    return aggregateExpenses(state, filters).byNecessity;
  }

  function aggregateExpenses(state, filters = {}) {
    assertValidState(state);
    const { localDate, localMonth } = filters;

    if (localDate !== undefined) {
      assertLocalDate(localDate);
    }
    if (localMonth !== undefined) {
      assertLocalMonth(localMonth);
    }
    if (localDate !== undefined && localMonth !== undefined) {
      throw new TypeError("Use either localDate or localMonth");
    }

    const byCategory = Object.fromEntries(
      CATEGORIES.map((category) => [category, 0])
    );
    const byNecessity = Object.fromEntries(
      NECESSITIES.map((necessity) => [necessity, 0])
    );
    let totalSen = 0;

    for (const expense of state.expenses) {
      if (
        localDate !== undefined &&
        expense.recordedLocalDate !== localDate
      ) {
        continue;
      }
      if (
        localMonth !== undefined &&
        !expense.recordedLocalDate.startsWith(`${localMonth}-`)
      ) {
        continue;
      }

      totalSen = safeAdd(totalSen, expense.amountSen);
      byCategory[expense.category] = safeAdd(
        byCategory[expense.category],
        expense.amountSen
      );
      byNecessity[expense.necessity] = safeAdd(
        byNecessity[expense.necessity],
        expense.amountSen
      );
    }

    return { totalSen, byCategory, byNecessity };
  }

  function normalizeExpenseInput(input) {
    if (!isRecord(input)) {
      throw new ExpenseValidationError("input_invalid");
    }

    const amountSen = parseAmountToSen(input.amount);
    const category = input.category;
    const necessity = input.necessity;

    if (!CATEGORIES.includes(category)) {
      throw new ExpenseValidationError("category_required");
    }
    if (!NECESSITIES.includes(necessity)) {
      throw new ExpenseValidationError("necessity_required");
    }
    if (input.note !== undefined && typeof input.note !== "string") {
      throw new ExpenseValidationError("note_invalid");
    }

    return {
      amountSen,
      category,
      necessity,
      note: normalizeNote(input.note || "")
    };
  }

  function normalizeNote(note) {
    return note.replace(/[\r\n]+/g, " ").trim();
  }

  function loadWritableState(storage) {
    if (!storage) {
      throw new StorageWriteBlockedError("storage_unavailable");
    }

    const result = loadState(storage);
    if (!result.canWrite) {
      throw new StorageWriteBlockedError("unsafe_stored_state");
    }

    return result.state;
  }

  function persistState(state, storage) {
    if (!isValidState(state)) {
      throw new StorageWriteBlockedError("invalid_outgoing_state");
    }

    const snapshot = cloneState(state);
    storage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    return snapshot;
  }

  function findExpense(state, expenseId) {
    if (!isNonEmptyString(expenseId)) {
      throw new ExpenseValidationError("id_invalid");
    }

    const expense = state.expenses.find(
      (candidate) => candidate.id === expenseId
    );
    if (!expense) {
      throw new ExpenseNotFoundError(expenseId);
    }
    return expense;
  }

  function safeAdd(left, right) {
    const result = left + right;
    if (!Number.isSafeInteger(result)) {
      throw new TypeError("Aggregate exceeds the safe integer range");
    }
    return result;
  }

  function isValidState(value) {
    if (
      !isRecord(value) ||
      value.schemaVersion !== SCHEMA_VERSION ||
      !Array.isArray(value.expenses)
    ) {
      return false;
    }

    const ids = new Set();
    for (const expense of value.expenses) {
      if (!isValidExpense(expense) || ids.has(expense.id)) {
        return false;
      }
      ids.add(expense.id);
    }
    return true;
  }

  function isValidExpense(expense) {
    return (
      isRecord(expense) &&
      isNonEmptyString(expense.id) &&
      Number.isSafeInteger(expense.amountSen) &&
      expense.amountSen > 0 &&
      CATEGORIES.includes(expense.category) &&
      NECESSITIES.includes(expense.necessity) &&
      typeof expense.note === "string" &&
      !/[\r\n]/.test(expense.note) &&
      isTimestamp(expense.recordedAt) &&
      isLocalDate(expense.recordedLocalDate) &&
      isTimestamp(expense.updatedAt)
    );
  }

  function isTimestamp(value) {
    return (
      typeof value === "string" &&
      value.length > 0 &&
      !Number.isNaN(Date.parse(value))
    );
  }

  function isLocalDate(value) {
    if (
      typeof value !== "string" ||
      !LOCAL_DATE_PATTERN.test(value)
    ) {
      return false;
    }

    const [year, month, day] = value.split("-").map(Number);
    const date = new Date(year, month - 1, day);
    return (
      date.getFullYear() === year &&
      date.getMonth() === month - 1 &&
      date.getDate() === day
    );
  }

  function isLocalMonth(value) {
    if (
      typeof value !== "string" ||
      !LOCAL_MONTH_PATTERN.test(value)
    ) {
      return false;
    }
    const [year, month] = value.split("-").map(Number);
    return (
      Number.isInteger(year) &&
      year >= 0 &&
      Number.isInteger(month) &&
      month >= 1 &&
      month <= 12
    );
  }

  function assertValidState(state) {
    if (!isValidState(state)) {
      throw new TypeError("State is invalid");
    }
  }

  function assertLocalDate(localDate) {
    if (!isLocalDate(localDate)) {
      throw new TypeError("Local date must be YYYY-MM-DD");
    }
  }

  function assertLocalMonth(localMonth) {
    if (!isLocalMonth(localMonth)) {
      throw new TypeError("Local month must be YYYY-MM");
    }
  }

  function isRecord(value) {
    return (
      typeof value === "object" &&
      value !== null &&
      !Array.isArray(value)
    );
  }

  function isNonEmptyString(value) {
    return typeof value === "string" && value.trim().length > 0;
  }

  function resolveDate(value) {
    const date =
      value === undefined
        ? new Date()
        : value instanceof Date
          ? new Date(value.getTime())
          : new Date(value);

    if (Number.isNaN(date.getTime())) {
      throw new TypeError("Date must be valid");
    }
    return date;
  }

  function cloneState(state) {
    return {
      schemaVersion: SCHEMA_VERSION,
      expenses: state.expenses.map((expense) => ({ ...expense }))
    };
  }

  function createLoadResult(status, canWrite, errorCode) {
    return {
      status,
      state: createEmptyState(),
      canWrite,
      errorCode
    };
  }

  function createExpenseId() {
    if (
      globalObject &&
      globalObject.crypto &&
      typeof globalObject.crypto.randomUUID === "function"
    ) {
      return globalObject.crypto.randomUUID();
    }

    return `expense-${Date.now().toString(36)}-${Math.random()
      .toString(36)
      .slice(2)}`;
  }

  function getBrowserStorage() {
    if (!globalObject) {
      return null;
    }

    try {
      return typeof globalObject.localStorage === "undefined"
        ? null
        : globalObject.localStorage;
    } catch {
      return null;
    }
  }

  const storageApi = Object.freeze({
    STORAGE_KEY,
    SCHEMA_VERSION,
    CATEGORIES,
    NECESSITIES,
    StorageWriteBlockedError,
    ExpenseNotFoundError,
    ExpenseValidationError,
    createEmptyState,
    loadState,
    addExpense,
    updateExpense,
    deleteExpense,
    parseAmountToSen,
    formatLocalDate,
    formatLocalMonth,
    getTodayExpenses,
    getExpensesForLocalDate,
    getDailyTotal,
    getMonthlyTotal,
    getMonthlyRegretTotal,
    getCategoryTotals,
    getNecessityTotals,
    aggregateExpenses
  });

  if (typeof module !== "undefined" && module.exports) {
    module.exports = storageApi;
  }

  if (globalObject) {
    globalObject.DailySpendStorage = storageApi;
  }
})(typeof globalThis === "undefined" ? this : globalThis);
