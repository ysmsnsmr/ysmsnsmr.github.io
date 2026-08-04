(function startOneNextTaskApp() {
  "use strict";

  const storageApi = window.OneNextTaskStorage;
  const elements = {
    topScreen: document.querySelector("#top-screen"),
    managementScreen: document.querySelector("#management-screen"),
    form: document.querySelector("#task-form"),
    input: document.querySelector("#task-input"),
    addButton: document.querySelector("#add-button"),
    manageButton: document.querySelector("#manage-button"),
    backButton: document.querySelector("#back-button"),
    completionCount: document.querySelector("#completion-count"),
    errorMessage: document.querySelector("#error-message"),
    currentView: document.querySelector("#current-view"),
    cycleView: document.querySelector("#cycle-view"),
    emptyView: document.querySelector("#empty-view"),
    blockedView: document.querySelector("#blocked-view"),
    taskText: document.querySelector("#task-text"),
    completeButton: document.querySelector("#complete-button"),
    deferButton: document.querySelector("#defer-button"),
    managementList: document.querySelector("#management-list"),
    managementEmpty: document.querySelector("#management-empty"),
    completedList: document.querySelector("#completed-list"),
    completedEmpty: document.querySelector("#completed-empty"),
    deletedList: document.querySelector("#deleted-list"),
    deletedEmpty: document.querySelector("#deleted-empty"),
    exportButton: document.querySelector("#export-button"),
    importInput: document.querySelector("#import-input"),
    dataStatus: document.querySelector("#data-status")
  };

  let state;
  let canWrite = false;
  let cycleEnded = false;
  let activeScreen = "top";
  // This is deliberately page-memory only: reloads always begin a new cycle.
  let seenTaskIds = new Set();
  let managementInputCount = 0;

  if (!storageApi) {
    state = { schemaVersion: 2, queueRuleVersion: 1, tasks: [] };
    showLoadError("unavailable");
    render();
    return;
  }

  const loadResult = syncStateFromStorage();

  if (canWrite) {
    beginCycle();
  } else {
    showLoadError(loadResult.status);
  }

  elements.form.addEventListener("submit", handleAdd);
  elements.completeButton.addEventListener("click", handleComplete);
  elements.deferButton.addEventListener("click", handleDefer);
  elements.manageButton.addEventListener("click", openManagement);
  elements.backButton.addEventListener("click", returnToTop);
  elements.managementList.addEventListener(
    "submit",
    handleManagementSubmit
  );
  elements.managementList.addEventListener(
    "click",
    handleManagementClick
  );
  elements.completedList.addEventListener(
    "click",
    handleManagementClick
  );
  elements.deletedList.addEventListener(
    "click",
    handleManagementClick
  );
  elements.exportButton.addEventListener("click", handleExport);
  elements.importInput.addEventListener("change", handleImport);

  render();

  function handleAdd(event) {
    event.preventDefault();
    if (!canWrite) {
      return;
    }

    const text = elements.input.value.trim();
    if (!text) {
      showError("用事を一行で入力してください。");
      elements.input.focus();
      return;
    }

    try {
      const nextState = storageApi.addTask(text);
      state = nextState;
      elements.input.value = "";
      clearError();
      if (cycleEnded) {
        beginCycle();
      }
      render();
      elements.input.focus();
    } catch (error) {
      handleWriteError(error);
    }
  }

  function handleComplete() {
    const currentTask = getCurrentTask();
    if (!currentTask) {
      return;
    }

    try {
      state = storageApi.completeTask(currentTask.id);
      clearError();
      render();
    } catch (error) {
      handleWriteError(error);
    }
  }

  function handleDefer() {
    const currentTask = getCurrentTask();
    if (!currentTask) {
      return;
    }

    try {
      const nextState = storageApi.deferTask(currentTask.id);
      const nextTask = storageApi.getNextTask(nextState);
      state = nextState;
      cycleEnded = Boolean(nextTask && seenTaskIds.has(nextTask.id));
      clearError();
      render();
    } catch (error) {
      handleWriteError(error);
    }
  }

  function openManagement() {
    if (!canWrite) {
      return;
    }

    activeScreen = "management";
    clearError();
    render();
  }

  function returnToTop() {
    const loadResult = syncStateFromStorage();
    activeScreen = "top";

    if (!loadResult.canWrite) {
      showLoadError(loadResult.status);
    }

    render();
  }

  function handleManagementSubmit(event) {
    event.preventDefault();
    if (!canWrite) {
      return;
    }

    const form = event.target;
    const taskId = form.dataset.taskId;
    const input = form.querySelector("input[name='task-text']");
    const text = input.value.trim();

    if (!taskId || !text) {
      showError("用事を一行で入力してください。");
      input.focus();
      return;
    }

    try {
      state = storageApi.editTask(taskId, text);
      clearError();
      render();
    } catch (error) {
      handleWriteError(error);
    }
  }

  function handleManagementClick(event) {
    const actionButton = event.target.closest("button[data-action]");
    if (!actionButton || !canWrite) {
      return;
    }

    const form = actionButton.closest("form[data-task-id]");
    const taskId = actionButton.dataset.taskId || form?.dataset.taskId;
    const action = actionButton.dataset.action;

    if (!taskId) {
      return;
    }

    if (action === "delete") {
      handleDelete(taskId);
      return;
    }

    if (action === "restore-completed") {
      handleRestoreCompleted(taskId);
      return;
    }

    if (action === "restore-deleted") {
      handleRestoreDeleted(taskId);
    }
  }

  function handleDelete(taskId) {
    const task = getActiveTasks().find(
      (candidate) => candidate.id === taskId
    );

    if (!task) {
      return;
    }

    if (
      !window.confirm(
        `「${task.text}」を削除しますか？7日以内なら元に戻せます。`
      )
    ) {
      return;
    }

    try {
      const wasCurrentTask = getCurrentTask()?.id === taskId;
      state = storageApi.deleteTask(taskId);
      seenTaskIds.delete(taskId);
      if (wasCurrentTask) {
        const nextTask = storageApi.getNextTask(state);
        cycleEnded = Boolean(nextTask && seenTaskIds.has(nextTask.id));
      }
      clearError();
      showDataStatus("削除しました。最近削除から元に戻せます。");
      render();
    } catch (error) {
      handleWriteError(error);
    }
  }

  function handleRestoreCompleted(taskId) {
    try {
      state = storageApi.restoreCompletedTask(taskId);
      beginCycle();
      clearError();
      showDataStatus("未完了のキュー末尾へ戻しました。");
      render();
    } catch (error) {
      handleWriteError(error);
    }
  }

  function handleRestoreDeleted(taskId) {
    const task = state.tasks.find((candidate) => candidate.id === taskId);
    if (!task || task.deletedAt === null) {
      return;
    }

    try {
      state = storageApi.restoreDeletedTask(taskId);
      if (task.status === "active") {
        seenTaskIds.delete(taskId);
        cycleEnded = false;
      }
      clearError();
      showDataStatus("削除を元に戻しました。");
      render();
    } catch (error) {
      handleWriteError(error);
    }
  }

  function handleExport() {
    clearDataStatus();

    try {
      const serialized = storageApi.exportState();
      const blob = new Blob([serialized], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `one-next-task-${formatDateForFilename(new Date())}.json`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      clearError();
      showDataStatus("JSONを書き出しました。");
    } catch {
      showError("データを書き出せませんでした。");
    }
  }

  async function handleImport() {
    const file = elements.importInput.files?.[0];
    if (!file || !canWrite) {
      elements.importInput.value = "";
      return;
    }

    clearDataStatus();
    if (
      !window.confirm(
        "現在のデータを、選んだJSONの内容に置き換えますか？"
      )
    ) {
      elements.importInput.value = "";
      return;
    }

    try {
      const serialized = await file.text();
      state = storageApi.importState(serialized);
      beginCycle();
      clearError();
      showDataStatus("JSONを読み込みました。");
      render();
    } catch (error) {
      if (error instanceof storageApi.InvalidImportError) {
        showError("このJSONは読み込めません。現在のデータは変更していません。");
        render();
      } else {
        handleWriteError(error);
      }
    } finally {
      elements.importInput.value = "";
    }
  }

  function beginCycle() {
    seenTaskIds = new Set();
    cycleEnded = false;
  }

  function getCurrentTask() {
    if (!canWrite || cycleEnded) {
      return null;
    }

    return storageApi.getNextTask(state);
  }

  function getActiveTasks() {
    return state.tasks
      .filter(
        (task) => task.status === "active" && task.deletedAt === null
      )
      .sort(
        (left, right) =>
          left.queueOrder - right.queueOrder ||
          left.createdAt.localeCompare(right.createdAt)
      );
  }

  function render() {
    if (!canWrite) {
      activeScreen = "top";
    }

    elements.topScreen.hidden = activeScreen !== "top";
    elements.managementScreen.hidden = activeScreen !== "management";
    elements.completionCount.textContent = canWrite
      ? `${storageApi.getTodayCompletionCount(state)}件`
      : "—";
    elements.input.disabled = !canWrite;
    elements.addButton.disabled = !canWrite;
    elements.manageButton.disabled = !canWrite;
    elements.completeButton.disabled = !canWrite;
    elements.deferButton.disabled = !canWrite;
    elements.exportButton.disabled = !canWrite;
    elements.importInput.disabled = !canWrite;

    if (activeScreen === "management") {
      renderManagement();
      return;
    }

    renderTop();
  }

  function renderTop() {
    hideTopTaskViews();

    if (!canWrite) {
      elements.blockedView.hidden = false;
      return;
    }

    const currentTask = storageApi.getNextTask(state);
    if (!currentTask) {
      elements.emptyView.hidden = false;
      return;
    }

    if (cycleEnded) {
      elements.cycleView.hidden = false;
      return;
    }

    elements.taskText.textContent = currentTask.text;
    seenTaskIds.add(currentTask.id);
    elements.currentView.hidden = false;
  }

  function renderManagement() {
    clearChildren(elements.managementList);
    clearChildren(elements.completedList);
    clearChildren(elements.deletedList);

    const activeTasks = getActiveTasks();
    const completedTasks = storageApi.getRecentCompletedTasks(state);
    const deletedTasks = storageApi.getRecentDeletedTasks(state);
    elements.managementEmpty.hidden = activeTasks.length !== 0;
    elements.completedEmpty.hidden = completedTasks.length !== 0;
    elements.deletedEmpty.hidden = deletedTasks.length !== 0;

    for (const task of activeTasks) {
      elements.managementList.append(createManagementItem(task));
    }

    for (const task of completedTasks) {
      elements.completedList.append(
        createHistoryItem(task, "restore-completed")
      );
    }

    for (const task of deletedTasks) {
      elements.deletedList.append(
        createHistoryItem(task, "restore-deleted")
      );
    }
  }

  function createManagementItem(task) {
    const item = document.createElement("li");
    const form = document.createElement("form");
    const label = document.createElement("label");
    const input = document.createElement("input");
    const actions = document.createElement("div");
    const saveButton = document.createElement("button");
    const deleteButton = document.createElement("button");
    const inputId = `management-task-${managementInputCount++}`;

    item.className = "management-item";
    form.className = "management-form";
    form.dataset.taskId = task.id;
    form.noValidate = true;

    label.htmlFor = inputId;
    label.textContent = "用事";

    input.id = inputId;
    input.name = "task-text";
    input.type = "text";
    input.value = task.text;
    input.autocomplete = "off";

    actions.className = "management-actions";

    saveButton.type = "submit";
    saveButton.textContent = "保存";

    deleteButton.type = "button";
    deleteButton.dataset.action = "delete";
    deleteButton.className = "delete-action";
    deleteButton.textContent = "削除";
    deleteButton.setAttribute("aria-label", `「${task.text}」を削除`);

    label.append(input);
    actions.append(saveButton, deleteButton);
    form.append(label, actions);
    item.append(form);
    return item;
  }

  function createHistoryItem(task, action) {
    const item = document.createElement("li");
    const text = document.createElement("p");
    const meta = document.createElement("p");
    const button = document.createElement("button");
    const isCompletion = action === "restore-completed";
    const timestamp = isCompletion ? task.completedAt : task.deletedAt;

    item.className = "history-item";
    text.className = "history-text";
    text.textContent = task.text;
    meta.className = "history-meta";
    meta.textContent = `${formatHistoryDate(timestamp)} ${
      isCompletion ? "完了" : "削除"
    }`;

    button.type = "button";
    button.dataset.action = action;
    button.dataset.taskId = task.id;
    button.textContent = "元に戻す";
    button.setAttribute("aria-label", `「${task.text}」を元に戻す`);

    item.append(text, meta, button);
    return item;
  }

  function formatHistoryDate(timestamp) {
    return new Intl.DateTimeFormat("ja-JP", {
      month: "numeric",
      day: "numeric"
    }).format(new Date(timestamp));
  }

  function formatDateForFilename(date) {
    const year = String(date.getFullYear()).padStart(4, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function clearChildren(element) {
    while (element.firstChild) {
      element.firstChild.remove();
    }
  }

  function hideTopTaskViews() {
    elements.currentView.hidden = true;
    elements.cycleView.hidden = true;
    elements.emptyView.hidden = true;
    elements.blockedView.hidden = true;
  }

  function handleWriteError(error) {
    const loadResult = syncStateFromStorage();
    if (!loadResult.canWrite) {
      showLoadError(loadResult.status);
      render();
      return;
    }

    const message =
      error instanceof TypeError
        ? "入力内容を確認してください。"
        : "保存できませんでした。変更は反映していません。";
    showError(message);
    render();
  }

  function syncStateFromStorage() {
    const result = storageApi.loadState();
    state = result.state;
    canWrite = result.canWrite;
    return result;
  }

  function showLoadError(status) {
    canWrite = false;

    const messages = {
      invalid:
        "保存データを読み込めません。データは変更しません。",
      unsupported_version:
        "新しい形式の保存データです。データは変更しません。",
      unavailable:
        "このブラウザでは保存を利用できません。"
    };

    showError(
      messages[status] ||
        "保存を利用できないため、操作を停止しました。"
    );
  }

  function showError(message) {
    elements.errorMessage.textContent = message;
    elements.errorMessage.hidden = false;
  }

  function clearError() {
    elements.errorMessage.textContent = "";
    elements.errorMessage.hidden = true;
  }

  function showDataStatus(message) {
    elements.dataStatus.textContent = message;
    elements.dataStatus.hidden = false;
  }

  function clearDataStatus() {
    elements.dataStatus.textContent = "";
    elements.dataStatus.hidden = true;
  }
})();

(function registerOneNextTaskServiceWorker() {
  "use strict";

  if (!("serviceWorker" in navigator)) {
    return;
  }

  window.addEventListener(
    "load",
    () => {
      navigator.serviceWorker
        .register("./service-worker.js", { scope: "./" })
        .then((registration) => {
          console.info("One Next Task offline support ready", registration.scope);
        })
        .catch((error) => {
          console.warn("One Next Task offline support unavailable", error);
        });
    },
    { once: true }
  );
})();
