(function attachDailySpendStorage(globalObject) {
  "use strict";

  const APP_ID = "daily-spend";
  const STORAGE_KEY = "daily-spend-state";
  const V1_BACKUP_KEY = "daily-spend-state-v1-pre-migration";
  const PRE_IMPORT_BACKUP_KEY = "daily-spend-state-before-import";
  const V2_ROLLBACK_BACKUP_KEY =
    "daily-spend-state-v2-before-rollback";
  const SCHEMA_VERSION = 2;
  const EXPORT_VERSION = 1;
  const HISTORY_DAYS = 30;

  const CATEGORY_DEFINITIONS = Object.freeze([
    Object.freeze({
      id: "daily-spend:dining",
      label: "Dining",
      legacyV1Value: "dining"
    }),
    Object.freeze({
      id: "daily-spend:groceries",
      label: "Groceries",
      legacyV1Value: "groceries"
    }),
    Object.freeze({
      id: "daily-spend:shopping",
      label: "Shopping",
      legacyV1Value: "shopping"
    }),
    Object.freeze({
      id: "daily-spend:health",
      label: "Health",
      legacyV1Value: "health"
    }),
    Object.freeze({
      id: "daily-spend:medical",
      label: "Medical",
      legacyV1Value: "medical"
    }),
    Object.freeze({
      id: "daily-spend:other",
      label: "Other",
      legacyV1Value: "other"
    })
  ]);
  const CATEGORY_IDS = Object.freeze(
    CATEGORY_DEFINITIONS.map((category) => category.id)
  );
  const CATEGORY_LABELS = Object.freeze(
    Object.fromEntries(
      CATEGORY_DEFINITIONS.map((category) => [
        category.id,
        category.label
      ])
    )
  );
  const V1_CATEGORY_TO_V2 = Object.freeze(
    Object.fromEntries(
      CATEGORY_DEFINITIONS.map((category) => [
        category.legacyV1Value,
        category.id
      ])
    )
  );
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

  class ImportValidationError extends Error {
    constructor(code) {
      super(`Daily Spend import failed: ${code}`);
      this.name = "ImportValidationError";
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
      return createLoadResult(
        "unavailable",
        false,
        "storage_read_failed",
        null,
        null
      );
    }

    let rawValue;
    try {
      rawValue = storage.getItem(STORAGE_KEY);
    } catch {
      return createLoadResult(
        "unavailable",
        false,
        "storage_read_failed",
        null,
        null
      );
    }

    if (rawValue === null) {
      return createLoadResult("empty", true, null, null, {
        status: "empty",
        schemaVersion: null,
        totalExpenseCount: 0,
        validExpenseCount: 0,
        invalidExpenseCount: 0,
        issues: []
      });
    }

    const diagnosis = diagnoseRawValue(rawValue);
    if (diagnosis.status === "invalid_json") {
      return createLoadResult(
        "invalid",
        false,
        "invalid_json",
        rawValue,
        diagnosis
      );
    }

    let parsed;
    try {
      parsed = JSON.parse(rawValue);
    } catch {
      return createLoadResult(
        "invalid",
        false,
        "invalid_json",
        rawValue,
        diagnosis
      );
    }

    if (
      isRecord(parsed) &&
      Number.isInteger(parsed.schemaVersion) &&
      parsed.schemaVersion > SCHEMA_VERSION
    ) {
      return createLoadResult(
        "unsupported_version",
        false,
        "unsupported_future_version",
        rawValue,
        diagnosis
      );
    }

    if (parsed.schemaVersion === 2) {
      if (diagnosis.issues.length > 0) {
        return createLoadResult(
          "invalid",
          false,
          "invalid_state",
          rawValue,
          diagnosis
        );
      }
      return {
        status: "ok",
        state: cloneState(parsed),
        canWrite: true,
        errorCode: null,
        rawValue,
        diagnosis
      };
    }

    if (parsed.schemaVersion === 1) {
      if (diagnosis.issues.length > 0) {
        return createLoadResult(
          "invalid",
          false,
          "invalid_state",
          rawValue,
          diagnosis
        );
      }

      try {
        ensureImmutableBackup(storage, V1_BACKUP_KEY, rawValue);
        const migratedState = migrateV1State(parsed);
        assertValidState(migratedState);
        storage.setItem(STORAGE_KEY, JSON.stringify(migratedState));
        return {
          status: "migrated",
          state: cloneState(migratedState),
          canWrite: true,
          errorCode: null,
          rawValue: JSON.stringify(migratedState),
          diagnosis: diagnoseStateV2(migratedState),
          migratedFromVersion: 1
        };
      } catch (error) {
        return createLoadResult(
          "migration_failed",
          false,
          error && error.code
            ? error.code
            : "migration_write_failed",
          rawValue,
          diagnosis
        );
      }
    }

    return createLoadResult(
      "invalid",
      false,
      "invalid_state",
      rawValue,
      diagnosis
    );
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

    return persistState(
      {
        schemaVersion: SCHEMA_VERSION,
        expenses: [
          ...state.expenses,
          {
            id,
            amountSen: normalized.amountSen,
            categoryId: normalized.categoryId,
            necessity: normalized.necessity,
            note: normalized.note,
            recordedAt: timestamp,
            recordedLocalDate: formatLocalDate(now),
            updatedAt: timestamp
          }
        ]
      },
      storage
    );
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
    const replacement = {
      ...existing,
      amountSen: normalized.amountSen,
      categoryId: normalized.categoryId,
      necessity: normalized.necessity,
      note: normalized.note,
      updatedAt: resolveDate(options.now).toISOString()
    };

    return persistState(
      {
        schemaVersion: SCHEMA_VERSION,
        expenses: state.expenses.map((expense) =>
          expense.id === expenseId ? replacement : expense
        )
      },
      storage
    );
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

  function restoreExpense(expense, storage = getBrowserStorage()) {
    const state = loadWritableState(storage);
    if (!isValidExpenseV2(expense)) {
      throw new ExpenseValidationError("restore_invalid");
    }
    if (state.expenses.some((candidate) => candidate.id === expense.id)) {
      throw new ExpenseValidationError("id_duplicate");
    }
    return persistState(
      {
        schemaVersion: SCHEMA_VERSION,
        expenses: [...state.expenses, { ...expense }]
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
      BigInt(ringgitPart) * 100n + BigInt(senPart.padEnd(2, "0"));

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
    return sortExpensesNewestFirst(
      state.expenses.filter(
        (expense) => expense.recordedLocalDate === localDate
      )
    ).map((expense) => ({ ...expense }));
  }

  function getRecentPastExpenses(
    state,
    date = new Date(),
    days = HISTORY_DAYS
  ) {
    assertValidState(state);
    if (!Number.isInteger(days) || days < 1 || days > 366) {
      throw new TypeError("History days must be between 1 and 366");
    }
    const now = resolveDate(date);
    const today = formatLocalDate(now);
    const oldest = formatLocalDate(
      new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate() - days,
        12,
        0,
        0,
        0
      )
    );
    return sortExpensesNewestFirst(
      state.expenses.filter(
        (expense) =>
          expense.recordedLocalDate >= oldest &&
          expense.recordedLocalDate < today
      )
    ).map((expense) => ({ ...expense }));
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
      CATEGORY_IDS.map((categoryId) => [categoryId, 0])
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
      byCategory[expense.categoryId] = safeAdd(
        byCategory[expense.categoryId],
        expense.amountSen
      );
      byNecessity[expense.necessity] = safeAdd(
        byNecessity[expense.necessity],
        expense.amountSen
      );
    }
    return { totalSen, byCategory, byNecessity };
  }

  function createExport(state, value = new Date()) {
    assertValidState(state);
    return {
      appId: APP_ID,
      exportVersion: EXPORT_VERSION,
      exportedAt: resolveDate(value).toISOString(),
      state: cloneState(state)
    };
  }

  function serializeExport(state, value = new Date()) {
    return `${JSON.stringify(createExport(state, value), null, 2)}\n`;
  }

  function importState(text, storage = getBrowserStorage()) {
    if (!storage) {
      throw new StorageWriteBlockedError("storage_unavailable");
    }
    const imported = parseImportText(text);

    let currentRaw;
    try {
      currentRaw = storage.getItem(STORAGE_KEY);
    } catch {
      throw new StorageWriteBlockedError("storage_read_failed");
    }

    let currentState = createEmptyState();
    if (currentRaw !== null) {
      const currentParsed = tryParseJson(currentRaw);
      if (currentParsed.ok && currentParsed.value.schemaVersion === 2) {
        if (diagnoseStateV2(currentParsed.value).issues.length === 0) {
          currentState = cloneState(currentParsed.value);
        } else {
          currentState = null;
        }
      } else if (
        currentParsed.ok &&
        currentParsed.value.schemaVersion === 1 &&
        diagnoseStateV1(currentParsed.value).issues.length === 0
      ) {
        ensureImmutableBackup(storage, V1_BACKUP_KEY, currentRaw);
        currentState = migrateV1State(currentParsed.value);
      } else {
        currentState = null;
      }
    }

    let nextState;
    let addedCount;
    let duplicateCount;
    if (currentState === null) {
      nextState = cloneState(imported.state);
      addedCount = nextState.expenses.length;
      duplicateCount = 0;
    } else {
      const merged = mergeStates(currentState, imported.state);
      nextState = merged.state;
      addedCount = merged.addedCount;
      duplicateCount = merged.duplicateCount;
    }

    assertValidState(nextState);
    if (currentRaw !== null && JSON.stringify(nextState) !== currentRaw) {
      writeVerifiedBackup(storage, PRE_IMPORT_BACKUP_KEY, currentRaw);
    }
    storage.setItem(STORAGE_KEY, JSON.stringify(nextState));
    return {
      state: cloneState(nextState),
      addedCount,
      duplicateCount,
      sourceSchemaVersion: imported.sourceSchemaVersion
    };
  }

  function parseImportText(text) {
    if (typeof text !== "string" || text.trim().length === 0) {
      throw new ImportValidationError("import_empty");
    }
    const parsed = tryParseJson(text);
    if (!parsed.ok) {
      throw new ImportValidationError("import_invalid_json");
    }

    let source = parsed.value;
    if (
      isRecord(source) &&
      ("exportVersion" in source || "appId" in source || "state" in source)
    ) {
      if (source.appId !== APP_ID) {
        throw new ImportValidationError("import_wrong_app");
      }
      if (source.exportVersion !== EXPORT_VERSION) {
        throw new ImportValidationError(
          source.exportVersion > EXPORT_VERSION
            ? "import_future_version"
            : "import_unsupported_version"
        );
      }
      source = source.state;
    }

    if (!isRecord(source)) {
      throw new ImportValidationError("import_invalid_state");
    }
    if (source.schemaVersion === 1) {
      if (diagnoseStateV1(source).issues.length > 0) {
        throw new ImportValidationError("import_invalid_state");
      }
      return {
        state: migrateV1State(source),
        sourceSchemaVersion: 1
      };
    }
    if (source.schemaVersion === 2) {
      if (diagnoseStateV2(source).issues.length > 0) {
        throw new ImportValidationError("import_invalid_state");
      }
      return { state: cloneState(source), sourceSchemaVersion: 2 };
    }
    if (
      Number.isInteger(source.schemaVersion) &&
      source.schemaVersion > SCHEMA_VERSION
    ) {
      throw new ImportValidationError("import_future_schema");
    }
    throw new ImportValidationError("import_invalid_state");
  }

  function getRawStoredValue(storage = getBrowserStorage()) {
    if (!storage) {
      throw new StorageWriteBlockedError("storage_unavailable");
    }
    try {
      return storage.getItem(STORAGE_KEY);
    } catch {
      throw new StorageWriteBlockedError("storage_read_failed");
    }
  }

  function diagnoseStoredData(storage = getBrowserStorage()) {
    return diagnoseRawValue(getRawStoredValue(storage));
  }

  function diagnoseRawValue(rawValue) {
    if (rawValue === null) {
      return {
        status: "empty",
        schemaVersion: null,
        totalExpenseCount: 0,
        validExpenseCount: 0,
        invalidExpenseCount: 0,
        issues: []
      };
    }
    if (typeof rawValue !== "string") {
      return diagnosisFromIssues("invalid", null, 0, [
        issue("$", "raw_not_string", "保存値が文字列ではありません。")
      ]);
    }
    const parsed = tryParseJson(rawValue);
    if (!parsed.ok) {
      return diagnosisFromIssues("invalid_json", null, 0, [
        issue("$", "invalid_json", "JSONとして解析できません。")
      ]);
    }
    const value = parsed.value;
    if (!isRecord(value)) {
      return diagnosisFromIssues("invalid", null, 0, [
        issue("$", "state_not_object", "保存データがobjectではありません。")
      ]);
    }
    if (value.schemaVersion === 1) {
      return diagnoseStateV1(value);
    }
    if (value.schemaVersion === 2) {
      return diagnoseStateV2(value);
    }
    if (
      Number.isInteger(value.schemaVersion) &&
      value.schemaVersion > SCHEMA_VERSION
    ) {
      return diagnosisFromIssues(
        "future_version",
        value.schemaVersion,
        Array.isArray(value.expenses) ? value.expenses.length : 0,
        [
          issue(
            "schemaVersion",
            "future_version",
            "このアプリより新しいschema versionです。"
          )
        ]
      );
    }
    return diagnosisFromIssues("invalid", value.schemaVersion ?? null, 0, [
      issue(
        "schemaVersion",
        "unsupported_schema",
        "schema versionを判定できません。"
      )
    ]);
  }

  function diagnoseStateV1(value) {
    return diagnoseState(value, 1, diagnoseExpenseV1);
  }

  function diagnoseStateV2(value) {
    return diagnoseState(value, 2, diagnoseExpenseV2);
  }

  function diagnoseState(value, expectedVersion, diagnoseExpense) {
    const issues = [];
    if (!isRecord(value)) {
      issues.push(issue("$", "state_not_object", "stateがobjectではありません。"));
      return diagnosisFromIssues("invalid", null, 0, issues);
    }
    if (value.schemaVersion !== expectedVersion) {
      issues.push(
        issue(
          "schemaVersion",
          "schema_mismatch",
          `schema version ${expectedVersion}ではありません。`
        )
      );
    }
    if (!Array.isArray(value.expenses)) {
      issues.push(
        issue("expenses", "expenses_not_array", "expensesが配列ではありません。")
      );
      return diagnosisFromIssues(
        "invalid",
        value.schemaVersion ?? null,
        0,
        issues
      );
    }

    const ids = new Map();
    value.expenses.forEach((expense, index) => {
      issues.push(...diagnoseExpense(expense, index));
      if (isRecord(expense) && isNonEmptyString(expense.id)) {
        if (ids.has(expense.id)) {
          issues.push(
            issue(
              `expenses[${index}].id`,
              "duplicate_id",
              `先の項目 ${ids.get(expense.id)} とIDが重複しています。`,
              index,
              expense.id
            )
          );
        } else {
          ids.set(expense.id, index);
        }
      }
    });

    const invalidIndexes = new Set(
      issues
        .map((entry) => entry.expenseIndex)
        .filter((index) => Number.isInteger(index))
    );
    return {
      status: issues.length === 0 ? "valid" : "invalid",
      schemaVersion: value.schemaVersion ?? null,
      totalExpenseCount: value.expenses.length,
      validExpenseCount: value.expenses.length - invalidIndexes.size,
      invalidExpenseCount: invalidIndexes.size,
      issues
    };
  }

  function diagnoseExpenseV1(expense, index) {
    const issues = diagnoseExpenseCommon(expense, index);
    if (!isRecord(expense)) {
      return issues;
    }
    if (!Object.prototype.hasOwnProperty.call(V1_CATEGORY_TO_V2, expense.category)) {
      issues.push(
        issue(
          `expenses[${index}].category`,
          "invalid_v1_category",
          "v1分類値が不正です。",
          index,
          expense.id
        )
      );
    }
    return issues;
  }

  function diagnoseExpenseV2(expense, index) {
    const issues = diagnoseExpenseCommon(expense, index);
    if (!isRecord(expense)) {
      return issues;
    }
    if (!CATEGORY_IDS.includes(expense.categoryId)) {
      issues.push(
        issue(
          `expenses[${index}].categoryId`,
          "invalid_category_id",
          "Daily Spendの分類IDではありません。",
          index,
          expense.id
        )
      );
    }
    return issues;
  }

  function diagnoseExpenseCommon(expense, index) {
    const issues = [];
    const base = `expenses[${index}]`;
    if (!isRecord(expense)) {
      return [
        issue(base, "expense_not_object", "項目がobjectではありません。", index)
      ];
    }
    const expenseId = expense.id;
    if (!isNonEmptyString(expenseId)) {
      issues.push(issue(`${base}.id`, "invalid_id", "IDが不正です。", index));
    }
    if (!Number.isSafeInteger(expense.amountSen) || expense.amountSen <= 0) {
      issues.push(
        issue(
          `${base}.amountSen`,
          "invalid_amount",
          "金額が正のsen整数ではありません。",
          index,
          expenseId
        )
      );
    }
    if (!NECESSITIES.includes(expense.necessity)) {
      issues.push(
        issue(
          `${base}.necessity`,
          "invalid_necessity",
          "必要度IDが不正です。",
          index,
          expenseId
        )
      );
    }
    if (typeof expense.note !== "string" || /[\r\n]/.test(expense.note)) {
      issues.push(
        issue(
          `${base}.note`,
          "invalid_note",
          "メモが一行の文字列ではありません。",
          index,
          expenseId
        )
      );
    }
    if (!isTimestamp(expense.recordedAt)) {
      issues.push(
        issue(
          `${base}.recordedAt`,
          "invalid_recorded_at",
          "記録日時が不正です。",
          index,
          expenseId
        )
      );
    }
    if (!isLocalDate(expense.recordedLocalDate)) {
      issues.push(
        issue(
          `${base}.recordedLocalDate`,
          "invalid_local_date",
          "現地日付が不正です。",
          index,
          expenseId
        )
      );
    }
    if (!isTimestamp(expense.updatedAt)) {
      issues.push(
        issue(
          `${base}.updatedAt`,
          "invalid_updated_at",
          "更新日時が不正です。",
          index,
          expenseId
        )
      );
    }
    return issues;
  }

  function rollbackToV1Backup(storage = getBrowserStorage()) {
    if (!storage) {
      throw new StorageWriteBlockedError("storage_unavailable");
    }
    let backupRaw;
    let currentRaw;
    try {
      backupRaw = storage.getItem(V1_BACKUP_KEY);
      currentRaw = storage.getItem(STORAGE_KEY);
    } catch {
      throw new StorageWriteBlockedError("storage_read_failed");
    }
    if (backupRaw === null) {
      throw new StorageWriteBlockedError("v1_backup_missing");
    }
    const parsed = tryParseJson(backupRaw);
    if (
      !parsed.ok ||
      !isRecord(parsed.value) ||
      parsed.value.schemaVersion !== 1 ||
      diagnoseStateV1(parsed.value).issues.length > 0
    ) {
      throw new StorageWriteBlockedError("v1_backup_invalid");
    }
    if (currentRaw === null) {
      throw new StorageWriteBlockedError("active_state_missing");
    }
    ensureImmutableBackup(
      storage,
      V2_ROLLBACK_BACKUP_KEY,
      currentRaw
    );
    storage.setItem(STORAGE_KEY, backupRaw);
    return JSON.parse(backupRaw);
  }

  function migrateV1State(v1State) {
    if (diagnoseStateV1(v1State).issues.length > 0) {
      throw new StorageWriteBlockedError("invalid_v1_state");
    }
    return {
      schemaVersion: SCHEMA_VERSION,
      expenses: v1State.expenses.map((expense) => ({
        id: expense.id,
        amountSen: expense.amountSen,
        categoryId: V1_CATEGORY_TO_V2[expense.category],
        necessity: expense.necessity,
        note: expense.note,
        recordedAt: expense.recordedAt,
        recordedLocalDate: expense.recordedLocalDate,
        updatedAt: expense.updatedAt
      }))
    };
  }

  function normalizeExpenseInput(input) {
    if (!isRecord(input)) {
      throw new ExpenseValidationError("input_invalid");
    }
    const amountSen = parseAmountToSen(input.amount);
    if (!CATEGORY_IDS.includes(input.categoryId)) {
      throw new ExpenseValidationError("category_required");
    }
    if (!NECESSITIES.includes(input.necessity)) {
      throw new ExpenseValidationError("necessity_required");
    }
    if (input.note !== undefined && typeof input.note !== "string") {
      throw new ExpenseValidationError("note_invalid");
    }
    return {
      amountSen,
      categoryId: input.categoryId,
      necessity: input.necessity,
      note: (input.note || "").replace(/[\r\n]+/g, " ").trim()
    };
  }

  function mergeStates(currentState, incomingState) {
    assertValidState(currentState);
    assertValidState(incomingState);
    const existingById = new Map(
      currentState.expenses.map((expense) => [expense.id, expense])
    );
    const additions = [];
    let duplicateCount = 0;
    for (const incoming of incomingState.expenses) {
      const existing = existingById.get(incoming.id);
      if (!existing) {
        additions.push({ ...incoming });
        continue;
      }
      if (JSON.stringify(existing) !== JSON.stringify(incoming)) {
        throw new ImportValidationError("import_id_conflict");
      }
      duplicateCount += 1;
    }
    return {
      state: {
        schemaVersion: SCHEMA_VERSION,
        expenses: [...currentState.expenses.map((expense) => ({ ...expense })), ...additions]
      },
      addedCount: additions.length,
      duplicateCount
    };
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
    assertValidState(state);
    const snapshot = cloneState(state);
    storage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    return snapshot;
  }

  function ensureImmutableBackup(storage, key, rawValue) {
    let existing;
    try {
      existing = storage.getItem(key);
      if (existing === null) {
        storage.setItem(key, rawValue);
        existing = storage.getItem(key);
      }
    } catch {
      throw new StorageWriteBlockedError("backup_write_failed");
    }
    if (existing !== rawValue) {
      throw new StorageWriteBlockedError("backup_conflict");
    }
  }

  function writeVerifiedBackup(storage, key, rawValue) {
    try {
      storage.setItem(key, rawValue);
      if (storage.getItem(key) !== rawValue) {
        throw new Error("backup mismatch");
      }
    } catch {
      throw new StorageWriteBlockedError("backup_write_failed");
    }
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

  function getCategoryLabel(categoryId) {
    return CATEGORY_LABELS[categoryId] || "Unknown";
  }

  function isValidState(value) {
    return diagnoseStateV2(value).issues.length === 0;
  }

  function isValidExpenseV2(value) {
    return diagnoseExpenseV2(value, 0).length === 0;
  }

  function assertValidState(state) {
    if (!isValidState(state)) {
      throw new StorageWriteBlockedError("invalid_outgoing_state");
    }
  }

  function assertLocalDate(value) {
    if (!isLocalDate(value)) {
      throw new TypeError("Local date must be YYYY-MM-DD");
    }
  }

  function assertLocalMonth(value) {
    if (!isLocalMonth(value)) {
      throw new TypeError("Local month must be YYYY-MM");
    }
  }

  function isTimestamp(value) {
    return (
      typeof value === "string" &&
      value.length > 0 &&
      !Number.isNaN(Date.parse(value))
    );
  }

  function isLocalDate(value) {
    if (typeof value !== "string" || !LOCAL_DATE_PATTERN.test(value)) {
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
    if (typeof value !== "string" || !LOCAL_MONTH_PATTERN.test(value)) {
      return false;
    }
    const [year, month] = value.split("-").map(Number);
    return year >= 0 && month >= 1 && month <= 12;
  }

  function isRecord(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
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

  function safeAdd(left, right) {
    const result = left + right;
    if (!Number.isSafeInteger(result)) {
      throw new TypeError("Aggregate exceeds the safe integer range");
    }
    return result;
  }

  function sortExpensesNewestFirst(expenses) {
    return [...expenses].sort(
      (left, right) =>
        right.recordedLocalDate.localeCompare(left.recordedLocalDate) ||
        right.recordedAt.localeCompare(left.recordedAt) ||
        right.id.localeCompare(left.id)
    );
  }

  function tryParseJson(value) {
    try {
      return { ok: true, value: JSON.parse(value) };
    } catch {
      return { ok: false, value: null };
    }
  }

  function issue(path, code, message, expenseIndex, expenseId) {
    const result = { path, code, message };
    if (Number.isInteger(expenseIndex)) {
      result.expenseIndex = expenseIndex;
    }
    if (isNonEmptyString(expenseId)) {
      result.expenseId = expenseId;
    }
    return result;
  }

  function diagnosisFromIssues(status, schemaVersion, total, issues) {
    const invalidIndexes = new Set(
      issues
        .map((entry) => entry.expenseIndex)
        .filter((index) => Number.isInteger(index))
    );
    return {
      status,
      schemaVersion,
      totalExpenseCount: total,
      validExpenseCount: Math.max(0, total - invalidIndexes.size),
      invalidExpenseCount: invalidIndexes.size,
      issues
    };
  }

  function cloneState(state) {
    return {
      schemaVersion: SCHEMA_VERSION,
      expenses: state.expenses.map((expense) => ({ ...expense }))
    };
  }

  function createLoadResult(
    status,
    canWrite,
    errorCode,
    rawValue,
    diagnosis
  ) {
    return {
      status,
      state: createEmptyState(),
      canWrite,
      errorCode,
      rawValue,
      diagnosis
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
    APP_ID,
    STORAGE_KEY,
    V1_BACKUP_KEY,
    PRE_IMPORT_BACKUP_KEY,
    V2_ROLLBACK_BACKUP_KEY,
    SCHEMA_VERSION,
    EXPORT_VERSION,
    HISTORY_DAYS,
    CATEGORY_DEFINITIONS,
    CATEGORY_IDS,
    NECESSITIES,
    StorageWriteBlockedError,
    ExpenseNotFoundError,
    ExpenseValidationError,
    ImportValidationError,
    createEmptyState,
    loadState,
    addExpense,
    updateExpense,
    deleteExpense,
    restoreExpense,
    parseAmountToSen,
    formatLocalDate,
    formatLocalMonth,
    getTodayExpenses,
    getExpensesForLocalDate,
    getRecentPastExpenses,
    getDailyTotal,
    getMonthlyTotal,
    getMonthlyRegretTotal,
    getCategoryTotals,
    getNecessityTotals,
    aggregateExpenses,
    getCategoryLabel,
    createExport,
    serializeExport,
    importState,
    parseImportText,
    getRawStoredValue,
    diagnoseStoredData,
    diagnoseRawValue,
    diagnoseStateV1,
    diagnoseStateV2,
    migrateV1State,
    rollbackToV1Backup
  });

  if (typeof module !== "undefined" && module.exports) {
    module.exports = storageApi;
  }
  if (globalObject) {
    globalObject.DailySpendStorage = storageApi;
  }
})(typeof globalThis === "undefined" ? this : globalThis);
