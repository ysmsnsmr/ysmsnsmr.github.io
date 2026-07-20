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
    managementEmpty: document.querySelector("#management-empty")
  };

  let state;
  let canWrite = false;
  let cycleEnded = false;
  let activeScreen = "top";
  // This is deliberately page-memory only: reloads always begin a new cycle.
  let seenTaskIds = new Set();
  let managementInputCount = 0;

  if (!storageApi) {
    state = { schemaVersion: 1, tasks: [] };
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
    const deleteButton = event.target.closest("button[data-action='delete']");
    if (!deleteButton || !canWrite) {
      return;
    }

    const form = deleteButton.closest("form[data-task-id]");
    const taskId = form?.dataset.taskId;
    const task = getActiveTasks().find(
      (candidate) => candidate.id === taskId
    );

    if (!taskId || !task) {
      return;
    }

    if (!window.confirm(`「${task.text}」を削除しますか？`)) {
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
      render();
    } catch (error) {
      handleWriteError(error);
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
      .filter((task) => task.status === "active")
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

    const activeTasks = getActiveTasks();
    elements.managementEmpty.hidden = activeTasks.length !== 0;

    for (const task of activeTasks) {
      elements.managementList.append(createManagementItem(task));
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
