(function startDailySpendApp() {
  "use strict";

  const storageApi = window.DailySpendStorage;
  const categoryLabels = Object.freeze({
    dining: "Dining",
    groceries: "Groceries",
    shopping: "Shopping",
    health: "Health",
    medical: "Medical",
    other: "Other"
  });
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

  const elements = {
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
    expenseList: document.querySelector("#expense-list")
  };

  let state;
  let canWrite = false;
  let editingId = null;

  if (!storageApi) {
    state = { schemaVersion: 1, expenses: [] };
    showLoadError("unavailable");
    render();
    return;
  }

  const initialLoad = syncStateFromStorage();
  if (!initialLoad.canWrite) {
    showLoadError(initialLoad.status);
  }

  elements.form.addEventListener("submit", handleSubmit);
  elements.cancelButton.addEventListener("click", cancelEditing);
  elements.expenseList.addEventListener("click", handleListClick);
  document.addEventListener("visibilitychange", handleVisibilityChange);

  render();

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
      render();
      elements.amount.focus();
    } catch (error) {
      handleOperationError(error);
    }
  }

  function handleListClick(event) {
    const button = event.target.closest("button[data-action][data-expense-id]");
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
      const amount = formatCurrency(expense.amountSen);
      if (!window.confirm(`${amount} の記録を削除しますか？`)) {
        return;
      }

      try {
        state = storageApi.deleteExpense(expense.id);
        if (editingId === expense.id) {
          resetForm();
        }
        showFeedback("記録を削除しました。", "success");
        render();
      } catch (error) {
        handleOperationError(error);
      }
    }
  }

  function startEditing(expense) {
    editingId = expense.id;
    elements.amount.value = senToInputValue(expense.amountSen);
    elements.note.value = expense.note;
    setCheckedValue("category", expense.category);
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
      category: formData.get("category"),
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

    const result = syncStateFromStorage();
    if (!result.canWrite) {
      showLoadError(result.status);
    }
    render();
  }

  function render() {
    const now = new Date();
    elements.todayLabel.textContent = dateFormatter.format(now);
    setFormDisabled(!canWrite);

    if (!canWrite) {
      elements.todayTotal.textContent = "—";
      elements.monthRegretTotal.textContent = "—";
      elements.todayCount.textContent = "—";
      elements.emptyMessage.hidden = true;
      clearChildren(elements.expenseList);
      return;
    }

    elements.todayTotal.textContent = formatCurrency(
      storageApi.getDailyTotal(state, now)
    );
    elements.monthRegretTotal.textContent = formatCurrency(
      storageApi.getMonthlyRegretTotal(state, now)
    );

    const todayExpenses = storageApi.getTodayExpenses(state, now);
    elements.todayCount.textContent = `${todayExpenses.length}件`;
    elements.emptyMessage.hidden = todayExpenses.length !== 0;
    clearChildren(elements.expenseList);

    for (const expense of todayExpenses) {
      elements.expenseList.append(createExpenseItem(expense));
    }
  }

  function createExpenseItem(expense) {
    const item = document.createElement("li");
    const main = document.createElement("div");
    const topRow = document.createElement("div");
    const amount = document.createElement("strong");
    const time = document.createElement("time");
    const tags = document.createElement("div");
    const category = document.createElement("span");
    const necessity = document.createElement("span");
    const actions = document.createElement("div");
    const editButton = document.createElement("button");
    const deleteButton = document.createElement("button");

    item.className = "expense-item";
    main.className = "expense-main";
    topRow.className = "expense-row";
    amount.className = "expense-amount";
    amount.textContent = formatCurrency(expense.amountSen);
    time.className = "expense-time";
    time.dateTime = expense.recordedAt;
    time.textContent = timeFormatter.format(new Date(expense.recordedAt));
    tags.className = "expense-tags";
    category.className = "expense-tag";
    category.textContent = categoryLabels[expense.category];
    necessity.className =
      `expense-tag expense-tag--${expense.necessity}`;
    necessity.textContent = necessityLabels[expense.necessity];
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

    topRow.append(amount, time);
    tags.append(category, necessity);
    main.append(topRow, tags);

    if (expense.note) {
      const note = document.createElement("p");
      note.className = "expense-note";
      note.textContent = expense.note;
      main.append(note);
    }

    actions.append(editButton, deleteButton);
    item.append(main, actions);
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
        note_invalid: "メモを確認してください。"
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
      elements.form.querySelector("input[name='category']").focus();
      return;
    }
    if (code === "necessity_required") {
      elements.form.querySelector("input[name='necessity']").focus();
      return;
    }
    elements.note.focus();
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
        "保存データを読み込めません。元データを守るため、操作を停止しました。",
      unsupported_version:
        "このアプリより新しい形式の保存データです。元データを守るため、操作を停止しました。",
      unavailable:
        "このブラウザでは端末内保存を利用できないため、操作を停止しました。"
    };
    showFeedback(
      messages[status] ||
        "保存を利用できないため、操作を停止しました。",
      "error"
    );
  }

  function setFormDisabled(disabled) {
    for (const control of elements.form.elements) {
      control.disabled = disabled;
    }
  }

  function showFeedback(message, tone) {
    elements.feedback.textContent = message;
    elements.feedback.dataset.tone = tone;
    elements.feedback.hidden = false;
  }

  function clearFeedback() {
    elements.feedback.textContent = "";
    delete elements.feedback.dataset.tone;
    elements.feedback.hidden = true;
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
