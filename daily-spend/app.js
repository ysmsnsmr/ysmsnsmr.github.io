(function startDailySpendApp() {
  "use strict";

  const storageApi = window.DailySpendStorage;
  const OFFICIAL_APP_URL =
    "https://zakkuri-spend.countryball.chatgpt.site/";
  const PORTFOLIO_HOST = "ysmsnsmr.github.io";
  const UNDO_WINDOW_MS = 8000;
  const necessityLabels = Object.freeze({
    needed: "必要だった",
    hesitated: "少し迷った",
    unnecessary: "なくてもよかった"
  });
  const currencyFormatter = new Intl.NumberFormat("en-MY", {
    style: "currency",
    currency: "MYR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
  const timeFormatter = new Intl.DateTimeFormat("ja-JP", {
    hour: "2-digit",
    minute: "2-digit"
  });
  const dateFormatter = new Intl.DateTimeFormat("ja-JP", {
    month: "numeric",
    day: "numeric",
    weekday: "short"
  });
  const historyDateFormatter = new Intl.DateTimeFormat("ja-JP", {
    month: "long",
    day: "numeric",
    weekday: "short"
  });

  const elements = {
    originNotice: document.querySelector("#origin-notice"),
    officialAppLink: document.querySelector("#official-app-link"),
    todayLabel: document.querySelector("#today-label"),
    todayTotal: document.querySelector("#today-total"),
    monthRegretTotal: document.querySelector("#month-regret-total"),
    feedback: document.querySelector("#feedback"),
    entryTitle: document.querySelector("#entry-title"),
    form: document.querySelector("#expense-form"),
    amount: document.querySelector("#amount"),
    note: document.querySelector("#note"),
    saveButton: document.querySelector("#save-button"),
    cancelButton: document.querySelector("#cancel-button"),
    todayCount: document.querySelector("#today-count"),
    emptyMessage: document.querySelector("#empty-message"),
    expenseList: document.querySelector("#expense-list"),
    historyCount: document.querySelector("#history-count"),
    historyEmpty: document.querySelector("#history-empty"),
    historyList: document.querySelector("#history-list"),
    exportButton: document.querySelector("#export-button"),
    importFile: document.querySelector("#import-file"),
    rawExportButton: document.querySelector("#raw-export-button"),
    diagnoseButton: document.querySelector("#diagnose-button"),
    recoveryPanel: document.querySelector("#recovery-panel"),
    diagnosisSummary: document.querySelector("#diagnosis-summary"),
    diagnosisList: document.querySelector("#diagnosis-list"),
    closeDiagnosisButton: document.querySelector(
      "#close-diagnosis-button"
    )
  };

  let state;
  let canWrite = false;
  let editingId = null;
  let lastLoadResult = null;
  let lastDeletedExpense = null;
  let undoTimer = null;

  configureOriginNotice();

  if (!storageApi) {
    state = { schemaVersion: 2, expenses: [] };
    showLoadError("unavailable");
    render();
    return;
  }

  const initialLoad = syncStateFromStorage();
  bindEvents();
  if (!initialLoad.canWrite) {
    showLoadError(initialLoad.status);
  } else if (initialLoad.status === "migrated") {
    showFeedback(
      "v1データを保護コピーして、新しい保存形式へ移行しました。",
      "success"
    );
  }
  render();

  function bindEvents() {
    elements.form.addEventListener("submit", handleSubmit);
    elements.cancelButton.addEventListener("click", cancelEditing);
    elements.expenseList.addEventListener("click", handleListClick);
    elements.exportButton.addEventListener("click", handleExport);
    elements.importFile.addEventListener("change", handleImport);
    elements.rawExportButton.addEventListener("click", handleRawExport);
    elements.diagnoseButton.addEventListener("click", showDiagnosis);
    elements.closeDiagnosisButton.addEventListener(
      "click",
      () => {
        elements.recoveryPanel.hidden = true;
      }
    );
    document.addEventListener("visibilitychange", handleVisibilityChange);
  }

  function configureOriginNotice() {
    if (
      !OFFICIAL_APP_URL ||
      window.location.hostname !== PORTFOLIO_HOST
    ) {
      return;
    }
    try {
      const officialUrl = new URL(OFFICIAL_APP_URL);
      if (officialUrl.origin === window.location.origin) {
        return;
      }
      elements.officialAppLink.href = officialUrl.href;
      elements.originNotice.hidden = false;
    } catch {
      elements.originNotice.hidden = true;
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (!canWrite) {
      return;
    }
    const input = getFormInput();
    try {
      if (editingId) {
        state = storageApi.updateExpense(editingId, input);
        resetForm();
        showFeedback("記録を更新しました。", "success");
      } else {
        state = storageApi.addExpense(input);
        resetForm();
        showFeedback("保存しました。", "success");
      }
      refreshLoadMetadata();
      render();
      elements.amount.focus();
    } catch (error) {
      handleOperationError(error);
    }
  }

  function handleListClick(event) {
    const button = event.target.closest(
      "button[data-action][data-expense-id]"
    );
    if (!button || !canWrite) {
      return;
    }
    const expenseId = button.dataset.expenseId;
    const expense = storageApi
      .getTodayExpenses(state)
      .find((candidate) => candidate.id === expenseId);
    if (!expense) {
      showFeedback(
        "この記録は今日の一覧にありません。画面を更新しました。",
        "error"
      );
      syncStateFromStorage();
      resetForm();
      render();
      return;
    }
    if (button.dataset.action === "edit") {
      startEditing(expense);
      return;
    }
    if (button.dataset.action === "delete") {
      try {
        state = storageApi.deleteExpense(expense.id);
        if (editingId === expense.id) {
          resetForm();
        }
        refreshLoadMetadata();
        showUndoFeedback(expense);
        render();
      } catch (error) {
        handleOperationError(error);
      }
    }
  }

  function showUndoFeedback(expense) {
    dismissUndo();
    lastDeletedExpense = { ...expense };
    clearChildren(elements.feedback);
    const message = document.createElement("span");
    const undoButton = document.createElement("button");
    message.textContent = `${formatCurrency(expense.amountSen)} を削除しました。`;
    undoButton.type = "button";
    undoButton.className = "feedback-action";
    undoButton.textContent = "元に戻す";
    undoButton.addEventListener("click", handleUndo, { once: true });
    elements.feedback.append(message, undoButton);
    elements.feedback.dataset.tone = "success";
    elements.feedback.hidden = false;
    undoTimer = window.setTimeout(() => {
      lastDeletedExpense = null;
      undoTimer = null;
      clearFeedback();
    }, UNDO_WINDOW_MS);
  }

  function handleUndo() {
    if (!lastDeletedExpense) {
      return;
    }
    const expense = { ...lastDeletedExpense };
    dismissUndo();
    try {
      state = storageApi.restoreExpense(expense);
      refreshLoadMetadata();
      showFeedback("削除した記録を元に戻しました。", "success");
      render();
    } catch (error) {
      handleOperationError(error);
    }
  }

  function dismissUndo() {
    if (undoTimer !== null) {
      window.clearTimeout(undoTimer);
    }
    undoTimer = null;
    lastDeletedExpense = null;
  }

  function startEditing(expense) {
    editingId = expense.id;
    elements.amount.value = senToInputValue(expense.amountSen);
    elements.note.value = expense.note;
    setCheckedValue("categoryId", expense.categoryId);
    setCheckedValue("necessity", expense.necessity);
    elements.entryTitle.textContent = "記録を編集";
    elements.saveButton.textContent = "更新する";
    elements.cancelButton.hidden = false;
    clearFeedback();
    document.querySelector(".entry-panel").scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
      block: "start"
    });
    elements.amount.focus({ preventScroll: true });
  }

  function cancelEditing() {
    resetForm();
    showFeedback("編集を取り消しました。", "success");
    render();
    elements.amount.focus();
  }

  function resetForm() {
    editingId = null;
    elements.form.reset();
    elements.entryTitle.textContent = "支払いを記録";
    elements.saveButton.textContent = "保存する";
    elements.cancelButton.hidden = true;
  }

  function getFormInput() {
    const formData = new FormData(elements.form);
    return {
      amount: elements.amount.value,
      categoryId: formData.get("categoryId"),
      necessity: formData.get("necessity"),
      note: elements.note.value
    };
  }

  function setCheckedValue(name, value) {
    const input = elements.form.querySelector(
      `input[name="${name}"][value="${value}"]`
    );
    if (input) {
      input.checked = true;
    }
  }

  function handleVisibilityChange() {
    if (document.visibilityState !== "visible" || editingId) {
      return;
    }
    dismissUndo();
    const result = syncStateFromStorage();
    if (!result.canWrite) {
      showLoadError(result.status);
    }
    render();
  }

  function handleExport() {
    if (!canWrite) {
      return;
    }
    try {
      const text = storageApi.serializeExport(state);
      downloadText(
        text,
        `daily-spend-${storageApi.formatLocalDate()}.json`,
        "application/json"
      );
      showFeedback("version付きJSONを書き出しました。", "success");
    } catch (error) {
      handleOperationError(error);
    }
  }

  async function handleImport() {
    const [file] = elements.importFile.files || [];
    if (!file) {
      return;
    }
    try {
      const text = await file.text();
      const result = storageApi.importState(text);
      state = result.state;
      canWrite = true;
      resetForm();
      refreshLoadMetadata();
      showFeedback(
        `${result.addedCount}件を読み込みました` +
          (result.duplicateCount > 0
            ? `（重複${result.duplicateCount}件は追加なし）。`
            : "。"),
        "success"
      );
      render();
    } catch (error) {
      handleImportError(error);
    } finally {
      elements.importFile.value = "";
    }
  }

  function handleImportError(error) {
    if (error instanceof storageApi.ImportValidationError) {
      const messages = {
        import_empty: "読み込むJSONが空です。",
        import_invalid_json: "JSONとして読み込めません。",
        import_wrong_app: "ざっくり出費の書き出しデータではありません。",
        import_future_version: "新しいexport versionのため読み込めません。",
        import_unsupported_version: "対応していないexport versionです。",
        import_future_schema: "新しいschema versionのため読み込めません。",
        import_invalid_state: "記録データの形式または項目に破損があります。",
        import_id_conflict: "同じIDで内容が異なる記録があるため中止しました。"
      };
      showFeedback(
        messages[error.code] || "JSONを読み込めませんでした。",
        "error"
      );
      return;
    }
    handleOperationError(error);
  }

  function handleRawExport() {
    try {
      const raw = storageApi.getRawStoredValue();
      if (raw === null) {
        showFeedback("保存されているrawデータはありません。", "error");
        return;
      }
      downloadText(
        raw,
        `daily-spend-raw-${storageApi.formatLocalDate()}.txt`,
        "text/plain"
      );
      showFeedback("保存値を変更せず、そのまま書き出しました。", "success");
    } catch (error) {
      handleOperationError(error);
    }
  }

  function showDiagnosis() {
    try {
      const diagnosis = storageApi.diagnoseStoredData();
      renderDiagnosis(diagnosis);
      elements.recoveryPanel.hidden = false;
      elements.recoveryPanel.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        block: "start"
      });
    } catch (error) {
      handleOperationError(error);
    }
  }

  function renderDiagnosis(diagnosis) {
    const version = diagnosis.schemaVersion ?? "不明";
    elements.diagnosisSummary.textContent =
      `状態: ${diagnosis.status} / schema: ${version} / ` +
      `全${diagnosis.totalExpenseCount}件 / ` +
      `正常${diagnosis.validExpenseCount}件 / ` +
      `破損${diagnosis.invalidExpenseCount}件`;
    clearChildren(elements.diagnosisList);
    if (diagnosis.issues.length === 0) {
      const item = document.createElement("li");
      item.textContent = "検出された問題はありません。";
      elements.diagnosisList.append(item);
      return;
    }
    for (const entry of diagnosis.issues.slice(0, 50)) {
      const item = document.createElement("li");
      const idPart = entry.expenseId ? ` / ID: ${entry.expenseId}` : "";
      item.textContent = `${entry.path}${idPart}: ${entry.message}`;
      elements.diagnosisList.append(item);
    }
    if (diagnosis.issues.length > 50) {
      const item = document.createElement("li");
      item.textContent = `ほか${diagnosis.issues.length - 50}件の問題があります。`;
      elements.diagnosisList.append(item);
    }
  }

  function render() {
    const now = new Date();
    elements.todayLabel.textContent = dateFormatter.format(now);
    setFormDisabled(!canWrite);
    elements.exportButton.disabled = !canWrite;
    elements.rawExportButton.disabled = !hasRawData();

    if (!canWrite) {
      elements.todayTotal.textContent = "—";
      elements.monthRegretTotal.textContent = "—";
      elements.todayCount.textContent = "—";
      elements.historyCount.textContent = "—";
      elements.emptyMessage.hidden = true;
      elements.historyEmpty.hidden = true;
      clearChildren(elements.expenseList);
      clearChildren(elements.historyList);
      return;
    }

    elements.todayTotal.textContent = formatCurrency(
      storageApi.getDailyTotal(state, now)
    );
    elements.monthRegretTotal.textContent = formatCurrency(
      storageApi.getMonthlyRegretTotal(state, now)
    );
    renderToday(now);
    renderHistory(now);
  }

  function renderToday(now) {
    const todayExpenses = storageApi.getTodayExpenses(state, now);
    elements.todayCount.textContent = `${todayExpenses.length}件`;
    elements.emptyMessage.hidden = todayExpenses.length !== 0;
    clearChildren(elements.expenseList);
    for (const expense of todayExpenses) {
      elements.expenseList.append(createExpenseItem(expense, true));
    }
  }

  function renderHistory(now) {
    const history = storageApi.getRecentPastExpenses(state, now);
    elements.historyCount.textContent = `${history.length}件`;
    elements.historyEmpty.hidden = history.length !== 0;
    clearChildren(elements.historyList);
    const groups = new Map();
    for (const expense of history) {
      const group = groups.get(expense.recordedLocalDate) || [];
      group.push(expense);
      groups.set(expense.recordedLocalDate, group);
    }
    for (const [localDate, expenses] of groups) {
      const section = document.createElement("section");
      const heading = document.createElement("h3");
      const list = document.createElement("ol");
      section.className = "history-day";
      heading.textContent = formatHistoryDate(localDate);
      list.className = "expense-list expense-list--history";
      for (const expense of expenses) {
        list.append(createExpenseItem(expense, false));
      }
      section.append(heading, list);
      elements.historyList.append(section);
    }
  }

  function createExpenseItem(expense, withActions) {
    const item = document.createElement("li");
    const main = document.createElement("div");
    const topRow = document.createElement("div");
    const amount = document.createElement("strong");
    const time = document.createElement("time");
    const tags = document.createElement("div");
    const category = document.createElement("span");
    const necessity = document.createElement("span");

    item.className = "expense-item";
    if (!withActions) {
      item.classList.add("expense-item--readonly");
    }
    main.className = "expense-main";
    topRow.className = "expense-row";
    amount.className = "expense-amount";
    amount.textContent = formatCurrency(expense.amountSen);
    time.className = "expense-time";
    time.dateTime = expense.recordedAt;
    time.textContent = timeFormatter.format(new Date(expense.recordedAt));
    tags.className = "expense-tags";
    category.className = "expense-tag";
    category.textContent = storageApi.getCategoryLabel(expense.categoryId);
    necessity.className = `expense-tag expense-tag--${expense.necessity}`;
    necessity.textContent = necessityLabels[expense.necessity];
    topRow.append(amount, time);
    tags.append(category, necessity);
    main.append(topRow, tags);

    if (expense.note) {
      const note = document.createElement("p");
      note.className = "expense-note";
      note.textContent = expense.note;
      main.append(note);
    }
    item.append(main);

    if (withActions) {
      const actions = document.createElement("div");
      const editButton = document.createElement("button");
      const deleteButton = document.createElement("button");
      actions.className = "expense-actions";
      editButton.type = "button";
      editButton.className = "record-action";
      editButton.dataset.action = "edit";
      editButton.dataset.expenseId = expense.id;
      editButton.textContent = "編集";
      editButton.setAttribute(
        "aria-label",
        `${formatCurrency(expense.amountSen)} の記録を編集`
      );
      deleteButton.type = "button";
      deleteButton.className = "record-action record-action--delete";
      deleteButton.dataset.action = "delete";
      deleteButton.dataset.expenseId = expense.id;
      deleteButton.textContent = "削除";
      deleteButton.setAttribute(
        "aria-label",
        `${formatCurrency(expense.amountSen)} の記録を削除`
      );
      actions.append(editButton, deleteButton);
      item.append(actions);
    }
    return item;
  }

  function handleOperationError(error) {
    if (error instanceof storageApi.ExpenseValidationError) {
      const messages = {
        amount_required: "金額を入力してください。",
        amount_invalid: "金額は数字と小数点以下2桁までで入力してください。",
        amount_positive: "0より大きい金額を入力してください。",
        amount_too_large: "金額が大きすぎます。",
        category_required: "分類を選んでください。",
        necessity_required: "必要度を選んでください。",
        note_invalid: "メモを確認してください。",
        restore_invalid: "削除した記録を復元できませんでした。",
        id_duplicate: "同じIDの記録がすでにあります。"
      };
      showFeedback(
        messages[error.code] || "入力内容を確認してください。",
        "error"
      );
      focusInvalidField(error.code);
      return;
    }
    const result = syncStateFromStorage();
    if (!result.canWrite) {
      resetForm();
      showLoadError(result.status);
      render();
      return;
    }
    showFeedback(
      "保存できませんでした。変更は反映していません。もう一度お試しください。",
      "error"
    );
    render();
  }

  function focusInvalidField(code) {
    if (code.startsWith("amount")) {
      elements.amount.focus();
      return;
    }
    if (code === "category_required") {
      elements.form.querySelector("input[name='categoryId']").focus();
      return;
    }
    if (code === "necessity_required") {
      elements.form.querySelector("input[name='necessity']").focus();
      return;
    }
    if (code === "note_invalid") {
      elements.note.focus();
    }
  }

  function syncStateFromStorage() {
    const result = storageApi.loadState();
    state = result.state;
    canWrite = result.canWrite;
    lastLoadResult = result;
    return result;
  }

  function refreshLoadMetadata() {
    const rawValue = storageApi.getRawStoredValue();
    lastLoadResult = {
      status: "ok",
      state,
      canWrite: true,
      errorCode: null,
      rawValue,
      diagnosis: storageApi.diagnoseRawValue(rawValue)
    };
  }

  function showLoadError(status) {
    canWrite = false;
    const messages = {
      invalid:
        "保存データに問題があります。raw保存と診断は利用できます。",
      unsupported_version:
        "新しい保存形式です。上書きを止めました。raw保存をご利用ください。",
      migration_failed:
        "v1の保護コピーまたは移行に失敗したため、上書きを止めました。",
      unavailable:
        "このブラウザでは端末内保存を利用できないため、操作を停止しました。"
    };
    showFeedback(
      messages[status] || "保存を利用できないため、操作を停止しました。",
      "error"
    );
  }

  function setFormDisabled(disabled) {
    for (const control of elements.form.elements) {
      control.disabled = disabled;
    }
  }

  function showFeedback(message, tone) {
    dismissUndo();
    clearChildren(elements.feedback);
    elements.feedback.textContent = message;
    elements.feedback.dataset.tone = tone;
    elements.feedback.hidden = false;
  }

  function clearFeedback() {
    clearChildren(elements.feedback);
    delete elements.feedback.dataset.tone;
    elements.feedback.hidden = true;
  }

  function hasRawData() {
    return Boolean(lastLoadResult && lastLoadResult.rawValue !== null);
  }

  function downloadText(text, filename, type) {
    const blob = new Blob([text], { type: `${type};charset=utf-8` });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  function formatHistoryDate(localDate) {
    const [year, month, day] = localDate.split("-").map(Number);
    return historyDateFormatter.format(new Date(year, month - 1, day, 12));
  }

  function clearChildren(element) {
    while (element.firstChild) {
      element.firstChild.remove();
    }
  }

  function formatCurrency(amountSen) {
    return currencyFormatter.format(amountSen / 100);
  }

  function senToInputValue(amountSen) {
    const ringgit = Math.floor(amountSen / 100);
    const sen = String(amountSen % 100).padStart(2, "0");
    return `${ringgit}.${sen}`;
  }
})();

(function registerDailySpendServiceWorker() {
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
          console.info(
            "Daily Spend offline support ready",
            registration.scope
          );
        })
        .catch((error) => {
          console.warn("Daily Spend offline support unavailable", error);
        });
    },
    { once: true }
  );
})();
