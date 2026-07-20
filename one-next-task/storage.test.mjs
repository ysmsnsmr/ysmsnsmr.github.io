import assert from "node:assert/strict";
import test from "node:test";
import storageApi from "./storage.js";

const {
  STORAGE_KEY,
  StorageWriteBlockedError,
  addTask,
  completeTask,
  createEmptyState,
  deferTask,
  deleteTask,
  editTask,
  getNextTask,
  getTodayCompletionCount,
  loadState
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

test("editing and deleting preserve unrelated tasks and queue order", () => {
  const { storage } = createMemoryStorage();
  const now = localDate(2026, 6, 19);

  addTask("first", storage, { id: "first", now });
  addTask("second", storage, { id: "second", now });
  const before = loadState(storage).state;
  const edited = editTask("second", "updated second", storage, {
    now: localDate(2026, 6, 19, 13)
  });
  const afterDelete = deleteTask("second", storage);

  assert.deepEqual(edited.tasks[0], before.tasks[0]);
  assert.equal(edited.tasks[1].text, "updated second");
  assert.equal(
    edited.tasks[1].queueOrder,
    before.tasks[1].queueOrder
  );
  assert.deepEqual(afterDelete.tasks, [before.tasks[0]]);
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
    schemaVersion: 2,
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
