import assert from "node:assert/strict";
import test from "node:test";
import storageApi from "./storage.js";

const {
  STORAGE_KEY,
  SCHEMA_VERSION,
  QUEUE_RULE_VERSION,
  InvalidImportError,
  StorageWriteBlockedError,
  addTask,
  completeTask,
  createEmptyState,
  deferTask,
  deleteTask,
  editTask,
  exportState,
  getNextTask,
  getRecentCompletedTasks,
  getRecentDeletedTasks,
  getTodayCompletionCount,
  importState,
  loadState,
  restoreCompletedTask,
  restoreDeletedTask
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

function localDate(year, monthIndex, day, hour = 12) {
  return new Date(year, monthIndex, day, hour, 0, 0, 0);
}

test("loads an empty state without writing", () => {
  const { state, storage } = createMemoryStorage();

  const result = loadState(storage);

  assert.equal(result.status, "empty");
  assert.equal(result.canWrite, true);
  assert.deepEqual(result.state, createEmptyState());
  assert.equal(state.setCalls, 0);
  assert.equal(state.lastKey, STORAGE_KEY);
});

test("adds, reloads, completes, and counts a task on its local day", () => {
  const { state, storage } = createMemoryStorage();
  const addedAt = localDate(2026, 6, 19, 9);
  const completedAt = localDate(2026, 6, 19, 20);

  const added = addTask("  牛乳を買う  ", storage, {
    id: "task-1",
    now: addedAt
  });
  const reloaded = loadState(storage);
  const completed = completeTask("task-1", storage, {
    now: completedAt
  });

  assert.equal(added.tasks[0].text, "牛乳を買う");
  assert.equal(added.tasks[0].status, "active");
  assert.equal(reloaded.status, "ok");
  assert.deepEqual(reloaded.state, added);
  assert.equal(completed.tasks[0].status, "completed");
  assert.equal(
    completed.tasks[0].completedAt,
    completedAt.toISOString()
  );
  assert.equal(
    completed.tasks[0].completedLocalDate,
    "2026-07-19"
  );
  assert.equal(
    getTodayCompletionCount(
      completed,
      localDate(2026, 6, 19, 23)
    ),
    1
  );
  assert.equal(
    getTodayCompletionCount(
      completed,
      localDate(2026, 6, 20, 0)
    ),
    0
  );
  assert.equal(state.setCalls, 2);
});

test("defers the oldest task behind the other active tasks", () => {
  const { storage } = createMemoryStorage();
  const firstTime = localDate(2026, 6, 19, 8);
  const secondTime = localDate(2026, 6, 19, 9);
  const thirdTime = localDate(2026, 6, 19, 10);

  addTask("first", storage, { id: "first", now: firstTime });
  addTask("second", storage, { id: "second", now: secondTime });
  addTask("third", storage, { id: "third", now: thirdTime });

  assert.equal(getNextTask(loadState(storage).state).id, "first");

  const deferred = deferTask("first", storage, {
    now: localDate(2026, 6, 19, 11)
  });

  assert.equal(getNextTask(deferred).id, "second");
  assert.deepEqual(
    deferred.tasks
      .filter((task) => task.status === "active")
      .sort((left, right) => left.queueOrder - right.queueOrder)
      .map((task) => task.id),
    ["second", "third", "first"]
  );
});

test("editing and soft deletion preserve unrelated tasks and queue order", () => {
  const { storage } = createMemoryStorage();
  const now = localDate(2026, 6, 19);

  addTask("first", storage, { id: "first", now });
  addTask("second", storage, { id: "second", now });
  const before = loadState(storage).state;
  const edited = editTask("second", "updated second", storage, {
    now: localDate(2026, 6, 19, 13)
  });
  const deletedAt = localDate(2026, 6, 19, 14);
  const afterDelete = deleteTask("second", storage, { now: deletedAt });

  assert.deepEqual(edited.tasks[0], before.tasks[0]);
  assert.equal(edited.tasks[1].text, "updated second");
  assert.equal(
    edited.tasks[1].queueOrder,
    before.tasks[1].queueOrder
  );
  assert.deepEqual(afterDelete.tasks[0], before.tasks[0]);
  assert.equal(afterDelete.tasks[1].id, "second");
  assert.equal(afterDelete.tasks[1].deletedAt, deletedAt.toISOString());
  assert.equal(afterDelete.tasks[1].queueOrder, before.tasks[1].queueOrder);
  assert.equal(getNextTask(afterDelete).id, "first");

  const restored = restoreDeletedTask("second", storage, {
    now: localDate(2026, 6, 19, 15)
  });

  assert.equal(restored.tasks[1].deletedAt, null);
  assert.equal(restored.tasks[1].queueOrder, before.tasks[1].queueOrder);
});

test("blocks writes and preserves invalid JSON", () => {
  const original = "{not-json";
  const { state, storage } = createMemoryStorage(original);

  const loaded = loadState(storage);

  assert.equal(loaded.status, "invalid");
  assert.equal(loaded.errorCode, "invalid_json");
  assert.equal(loaded.canWrite, false);
  assert.throws(
    () =>
      addTask("must not be stored", storage, {
        id: "blocked",
        now: localDate(2026, 6, 19)
      }),
    (error) =>
      error instanceof StorageWriteBlockedError &&
      error.code === "unsafe_stored_state"
  );
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("blocks writes and preserves future-version data", () => {
  const original = JSON.stringify({
    schemaVersion: SCHEMA_VERSION + 1,
    tasks: [],
    futureField: true
  });
  const { state, storage } = createMemoryStorage(original);

  const loaded = loadState(storage);

  assert.equal(loaded.status, "unsupported_version");
  assert.equal(loaded.errorCode, "unsupported_future_version");
  assert.equal(loaded.canWrite, false);
  assert.throws(
    () =>
      addTask("must not be stored", storage, {
        id: "blocked",
        now: localDate(2026, 6, 19)
      }),
    StorageWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("migrates schema version 1 in memory without writing", () => {
  const timestamp = localDate(2026, 6, 19).toISOString();
  const original = JSON.stringify({
    schemaVersion: 1,
    tasks: [
      {
        id: "legacy",
        text: "legacy task",
        status: "active",
        createdAt: timestamp,
        updatedAt: timestamp,
        completedAt: null,
        queueOrder: 1,
        completedLocalDate: null
      }
    ]
  });
  const { state, storage } = createMemoryStorage(original);

  const loaded = loadState(storage);

  assert.equal(loaded.status, "ok");
  assert.equal(loaded.state.schemaVersion, SCHEMA_VERSION);
  assert.equal(loaded.state.queueRuleVersion, QUEUE_RULE_VERSION);
  assert.equal(loaded.state.tasks[0].deletedAt, null);
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("blocks writes for a future queue rule version", () => {
  const original = JSON.stringify({
    schemaVersion: SCHEMA_VERSION,
    queueRuleVersion: QUEUE_RULE_VERSION + 1,
    tasks: []
  });
  const { state, storage } = createMemoryStorage(original);

  const loaded = loadState(storage);

  assert.equal(loaded.status, "unsupported_version");
  assert.equal(loaded.errorCode, "unsupported_future_queue_rule");
  assert.equal(loaded.canWrite, false);
  assert.throws(
    () => addTask("blocked", storage, { id: "blocked" }),
    StorageWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("blocks writes when schema version 1 data is malformed", () => {
  const original = JSON.stringify({
    schemaVersion: 1,
    tasks: [{ id: "incomplete" }]
  });
  const { state, storage } = createMemoryStorage(original);

  const loaded = loadState(storage);

  assert.equal(loaded.status, "invalid");
  assert.equal(loaded.errorCode, "invalid_state");
  assert.equal(loaded.canWrite, false);
  assert.throws(
    () =>
      addTask("must not be stored", storage, {
        id: "blocked",
        now: localDate(2026, 6, 19)
      }),
    StorageWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
  assert.equal(state.value, original);
});

test("reports unavailable storage and blocks mutations after read failure", () => {
  const { state, storage } = createMemoryStorage(null, {
    failOnGet: true
  });

  const loaded = loadState(storage);

  assert.equal(loaded.status, "unavailable");
  assert.equal(loaded.errorCode, "storage_read_failed");
  assert.equal(loaded.canWrite, false);
  assert.throws(
    () =>
      addTask("must not be stored", storage, {
        id: "blocked",
        now: localDate(2026, 6, 19)
      }),
    StorageWriteBlockedError
  );
  assert.equal(state.setCalls, 0);
});

test("does not alter stored data when a write fails", () => {
  const { state, storage } = createMemoryStorage(null, {
    failOnSet: true
  });

  assert.throws(
    () =>
      addTask("cannot be stored", storage, {
        id: "task-1",
        now: localDate(2026, 6, 19)
      }),
    /quota exceeded/
  );
  assert.equal(state.value, null);
  assert.equal(state.setCalls, 1);
});

test("lists recent completed tasks and restores one at the queue tail", () => {
  const { storage } = createMemoryStorage();
  const now = localDate(2026, 6, 20, 12);

  addTask("still active", storage, {
    id: "active",
    now: localDate(2026, 6, 10)
  });
  addTask("recently done", storage, {
    id: "recent",
    now: localDate(2026, 6, 11)
  });
  addTask("old done", storage, {
    id: "old",
    now: localDate(2026, 6, 1)
  });
  completeTask("recent", storage, {
    now: localDate(2026, 6, 19, 12)
  });
  completeTask("old", storage, {
    now: localDate(2026, 6, 12, 11)
  });

  const beforeRestore = loadState(storage).state;
  assert.deepEqual(
    getRecentCompletedTasks(beforeRestore, { now }).map((task) => task.id),
    ["recent"]
  );

  const restored = restoreCompletedTask("recent", storage, { now });
  const restoredTask = restored.tasks.find((task) => task.id === "recent");

  assert.equal(restoredTask.status, "active");
  assert.equal(restoredTask.completedAt, null);
  assert.equal(restoredTask.completedLocalDate, null);
  assert.ok(
    restoredTask.queueOrder >
      Math.max(...beforeRestore.tasks.map((task) => task.queueOrder))
  );
  assert.equal(getNextTask(restored).id, "active");
});

test("lists only recently deleted tasks and restores them", () => {
  const { storage } = createMemoryStorage();
  const now = localDate(2026, 6, 20, 12);

  addTask("recently deleted", storage, {
    id: "recent-delete",
    now: localDate(2026, 6, 10)
  });
  addTask("old deleted", storage, {
    id: "old-delete",
    now: localDate(2026, 6, 1)
  });
  deleteTask("recent-delete", storage, {
    now: localDate(2026, 6, 19, 12)
  });
  deleteTask("old-delete", storage, {
    now: localDate(2026, 6, 12, 11)
  });

  const deleted = loadState(storage).state;
  assert.deepEqual(
    getRecentDeletedTasks(deleted, { now }).map((task) => task.id),
    ["recent-delete"]
  );

  const restored = restoreDeletedTask("recent-delete", storage, { now });
  assert.equal(
    restored.tasks.find((task) => task.id === "recent-delete").deletedAt,
    null
  );
});

test("exports and imports a validated versioned snapshot", () => {
  const source = createMemoryStorage();
  addTask("backup me", source.storage, {
    id: "backup",
    now: localDate(2026, 6, 19)
  });

  const exported = exportState(source.storage);
  const parsed = JSON.parse(exported);
  const destination = createMemoryStorage();
  const imported = importState(exported, destination.storage);

  assert.equal(parsed.schemaVersion, SCHEMA_VERSION);
  assert.equal(parsed.queueRuleVersion, QUEUE_RULE_VERSION);
  assert.deepEqual(imported, loadState(source.storage).state);
  assert.deepEqual(loadState(destination.storage).state, imported);
  assert.equal(destination.state.setCalls, 1);
});

test("rejects invalid imports without changing existing data", () => {
  const { state, storage } = createMemoryStorage();
  addTask("keep me", storage, {
    id: "existing",
    now: localDate(2026, 6, 19)
  });
  const original = state.value;
  const setCalls = state.setCalls;

  assert.throws(
    () => importState("{broken", storage),
    (error) =>
      error instanceof InvalidImportError &&
      error.code === "invalid_json"
  );
  assert.throws(
    () =>
      importState(
        JSON.stringify({
          schemaVersion: SCHEMA_VERSION + 1,
          tasks: []
        }),
        storage
      ),
    (error) =>
      error instanceof InvalidImportError &&
      error.code === "unsupported_future_version"
  );
  assert.equal(state.value, original);
  assert.equal(state.setCalls, setCalls);
});
