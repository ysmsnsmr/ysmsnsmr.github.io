(function attachOneNextTaskStorage(globalObject) {
  "use strict";

  const STORAGE_KEY = "one-next-task-state";
  const SCHEMA_VERSION = 1;
  const ACTIVE_STATUS = "active";
  const COMPLETED_STATUS = "completed";
  const LOCAL_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

  class StorageWriteBlockedError extends Error {
    constructor(code) {
      super(`One Next Task write blocked: ${code}`);
      this.name = "StorageWriteBlockedError";
      this.code = code;
    }
  }

  class TaskNotFoundError extends Error {
    constructor(taskId) {
      super(`Task not found: ${taskId}`);
      this.name = "TaskNotFoundError";
      this.taskId = taskId;
    }
  }

  function createEmptyState() {
    return {
      schemaVersion: SCHEMA_VERSION,
      tasks: []
    };
  }

  function loadState(storage = getBrowserStorage()) {
    if (!storage) {
      return createLoadResult(
        "unavailable",
        false,
        "storage_read_failed"
      );
    }

    let storedValue;
    try {
      storedValue = storage.getItem(STORAGE_KEY);
    } catch {
      return createLoadResult(
        "unavailable",
        false,
        "storage_read_failed"
      );
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

  function addTask(
    text,
    storage = getBrowserStorage(),
    options = {}
  ) {
    const state = loadWritableState(storage);
    const normalizedText = normalizeTaskText(text);
    const now = resolveDate(options.now);
    const nowIso = now.toISOString();
    const taskId =
      options.id === undefined ? createTaskId() : options.id;

    if (!isNonEmptyString(taskId)) {
      throw new TypeError("Task id must be a non-empty string");
    }
    if (state.tasks.some((task) => task.id === taskId)) {
      throw new TypeError(`Task id already exists: ${taskId}`);
    }

    const nextState = {
      schemaVersion: SCHEMA_VERSION,
      tasks: [
        ...state.tasks,
        {
          id: taskId,
          text: normalizedText,
          status: ACTIVE_STATUS,
          createdAt: nowIso,
          updatedAt: nowIso,
          completedAt: null,
          queueOrder: nextQueueOrder(state.tasks),
          completedLocalDate: null
        }
      ]
    };

    return persistState(nextState, storage);
  }

  function completeTask(
    taskId,
    storage = getBrowserStorage(),
    options = {}
  ) {
    const state = loadWritableState(storage);
    const task = findTask(state, taskId);

    if (task.status === COMPLETED_STATUS) {
      return state;
    }

    const now = resolveDate(options.now);
    const nowIso = now.toISOString();
    const nextState = replaceTask(state, taskId, {
      ...task,
      status: COMPLETED_STATUS,
      updatedAt: nowIso,
      completedAt: nowIso,
      completedLocalDate: formatLocalDate(now)
    });

    return persistState(nextState, storage);
  }

  function deferTask(
    taskId,
    storage = getBrowserStorage(),
    options = {}
  ) {
    const state = loadWritableState(storage);
    const task = findTask(state, taskId);

    if (task.status !== ACTIVE_STATUS) {
      throw new TypeError("Only active tasks can be deferred");
    }

    const nowIso = resolveDate(options.now).toISOString();
    const nextState = replaceTask(state, taskId, {
      ...task,
      updatedAt: nowIso,
      queueOrder: nextQueueOrder(state.tasks)
    });

    return persistState(nextState, storage);
  }

  function editTask(
    taskId,
    text,
    storage = getBrowserStorage(),
    options = {}
  ) {
    const state = loadWritableState(storage);
    const task = findTask(state, taskId);
    const nextState = replaceTask(state, taskId, {
      ...task,
      text: normalizeTaskText(text),
      updatedAt: resolveDate(options.now).toISOString()
    });

    return persistState(nextState, storage);
  }

  function deleteTask(taskId, storage = getBrowserStorage()) {
    const state = loadWritableState(storage);
    findTask(state, taskId);

    const nextState = {
      schemaVersion: SCHEMA_VERSION,
      tasks: state.tasks.filter((task) => task.id !== taskId)
    };

    return persistState(nextState, storage);
  }

  function getNextTask(state) {
    assertValidState(state);

    const activeTasks = state.tasks
      .filter((task) => task.status === ACTIVE_STATUS)
      .sort(
        (left, right) =>
          left.queueOrder - right.queueOrder ||
          left.createdAt.localeCompare(right.createdAt)
      );

    return activeTasks[0] ? { ...activeTasks[0] } : null;
  }

  function getTodayCompletionCount(state, date = new Date()) {
    assertValidState(state);
    const localDate = formatLocalDate(resolveDate(date));

    return state.tasks.filter(
      (task) =>
        task.status === COMPLETED_STATUS &&
        task.completedLocalDate === localDate
    ).length;
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

  function replaceTask(state, taskId, replacement) {
    return {
      schemaVersion: SCHEMA_VERSION,
      tasks: state.tasks.map((task) =>
        task.id === taskId ? replacement : task
      )
    };
  }

  function findTask(state, taskId) {
    if (!isNonEmptyString(taskId)) {
      throw new TypeError("Task id must be a non-empty string");
    }

    const task = state.tasks.find((candidate) => candidate.id === taskId);
    if (!task) {
      throw new TaskNotFoundError(taskId);
    }

    return task;
  }

  function nextQueueOrder(tasks) {
    const highestOrder = tasks.reduce(
      (highest, task) => Math.max(highest, task.queueOrder),
      0
    );

    if (highestOrder >= Number.MAX_SAFE_INTEGER) {
      throw new StorageWriteBlockedError("invalid_outgoing_state");
    }

    return highestOrder + 1;
  }

  function normalizeTaskText(text) {
    if (typeof text !== "string") {
      throw new TypeError("Task text must be a string");
    }

    const normalized = text.replace(/[\r\n]+/g, " ").trim();
    if (normalized.length === 0) {
      throw new TypeError("Task text must not be empty");
    }

    return normalized;
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

  function formatLocalDate(date) {
    const year = String(date.getFullYear()).padStart(4, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function isValidState(value) {
    if (
      !isRecord(value) ||
      value.schemaVersion !== SCHEMA_VERSION ||
      !Array.isArray(value.tasks)
    ) {
      return false;
    }

    const ids = new Set();
    const queueOrders = new Set();

    for (const task of value.tasks) {
      if (!isValidTask(task)) {
        return false;
      }
      if (ids.has(task.id) || queueOrders.has(task.queueOrder)) {
        return false;
      }
      ids.add(task.id);
      queueOrders.add(task.queueOrder);
    }

    return true;
  }

  function isValidTask(task) {
    if (
      !isRecord(task) ||
      !isNonEmptyString(task.id) ||
      !isNonEmptyString(task.text) ||
      !isTimestamp(task.createdAt) ||
      !isTimestamp(task.updatedAt) ||
      !Number.isSafeInteger(task.queueOrder) ||
      task.queueOrder < 1
    ) {
      return false;
    }

    if (task.status === ACTIVE_STATUS) {
      return (
        task.completedAt === null &&
        task.completedLocalDate === null
      );
    }

    if (task.status === COMPLETED_STATUS) {
      return (
        isTimestamp(task.completedAt) &&
        isLocalDate(task.completedLocalDate)
      );
    }

    return false;
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

  function isNonEmptyString(value) {
    return typeof value === "string" && value.trim().length > 0;
  }

  function isRecord(value) {
    return (
      typeof value === "object" &&
      value !== null &&
      !Array.isArray(value)
    );
  }

  function assertValidState(state) {
    if (!isValidState(state)) {
      throw new TypeError("State is invalid");
    }
  }

  function cloneState(state) {
    return {
      schemaVersion: SCHEMA_VERSION,
      tasks: state.tasks.map((task) => ({ ...task }))
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

  function createTaskId() {
    if (
      globalObject.crypto &&
      typeof globalObject.crypto.randomUUID === "function"
    ) {
      return globalObject.crypto.randomUUID();
    }

    return `task-${Date.now().toString(36)}-${Math.random()
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
    StorageWriteBlockedError,
    TaskNotFoundError,
    createEmptyState,
    loadState,
    addTask,
    completeTask,
    deferTask,
    editTask,
    deleteTask,
    getNextTask,
    getTodayCompletionCount
  });

  if (typeof module !== "undefined" && module.exports) {
    module.exports = storageApi;
  }

  if (globalObject) {
    globalObject.OneNextTaskStorage = storageApi;
  }
})(typeof globalThis === "undefined" ? this : globalThis);
