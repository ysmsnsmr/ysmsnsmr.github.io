const board = document.getElementById("board");
const movesLabel = document.getElementById("moves");
const missesLabel = document.getElementById("misses");
const ripenessLabel = document.getElementById("ripeness");
const bestScoreLabel = document.getElementById("best-score");
const ripenessFill = document.getElementById("ripeness-fill");
const phaseLabel = document.getElementById("phase-label");
const statusLabel = document.getElementById("status");
const peach = document.getElementById("peach");
const juiceLayer = document.getElementById("juice-layer");
const restartButton = document.getElementById("restart-button");
const resultRestartButton = document.getElementById("result-restart-button");
const result = document.getElementById("result");
const resultRank = document.getElementById("result-rank");
const resultTitle = document.getElementById("result-title");
const resultDetail = document.getElementById("result-detail");

const bestKey = "peach-orchard-memory-best";
const motifs = [
  { id: "white", label: "白桃", glyph: "白", tone: "#ffd8c3", ink: "#b85161" },
  { id: "leaf", label: "葉", glyph: "葉", tone: "#cfe5b2", ink: "#3e7d62" },
  { id: "rain", label: "雨粒", glyph: "雨", tone: "#c6dfea", ink: "#4e788d" },
  { id: "fuzz", label: "産毛", glyph: "毛", tone: "#ead0ba", ink: "#9a674f" },
  { id: "honey", label: "蜜", glyph: "蜜", tone: "#f6d37b", ink: "#8a6120" },
  { id: "dusk", label: "夕焼け", glyph: "夕", tone: "#e7a0a3", ink: "#97435c" },
  { id: "seed", label: "種", glyph: "種", tone: "#d5b18a", ink: "#6f5239" },
  { id: "flower", label: "花", glyph: "花", tone: "#f2c3d4", ink: "#a84e74" }
];

let cards = [];
let openCards = [];
let matchedPairs = 0;
let moves = 0;
let misses = 0;
let ripeness = 100;
let inputLocked = false;
let completionTimer = 0;

bestScoreLabel.textContent = String(loadBestScore());
restartButton.addEventListener("click", startGame);
resultRestartButton.addEventListener("click", startGame);
startGame();

function startGame() {
  clearTimeout(completionTimer);
  cards = shuffle([...motifs, ...motifs].map((motif, index) => ({
    ...motif,
    uid: `${motif.id}-${index}`
  })));
  openCards = [];
  matchedPairs = 0;
  moves = 0;
  misses = 0;
  ripeness = 100;
  inputLocked = false;
  result.classList.remove("is-visible");
  result.setAttribute("aria-hidden", "true");
  peach.className = "peach";
  statusLabel.textContent = "桃の札を2枚めくってください";
  renderBoard();
  renderStats();
  renderGrowth();
}

function renderBoard() {
  board.replaceChildren();

  cards.forEach((card, index) => {
    const button = document.createElement("button");
    button.className = "card";
    button.type = "button";
    button.dataset.index = String(index);
    button.setAttribute("aria-label", "桃の札");
    button.innerHTML = `
      <span class="card__inner">
        <span class="card__face card__back" aria-hidden="true"></span>
        <span class="card__face card__front">
          <span class="card__glyph">${card.glyph}</span>
          <span class="card__label">${card.label}</span>
        </span>
      </span>
    `;
    button.style.setProperty("--card-tone", card.tone);
    button.style.setProperty("--card-ink", card.ink);
    button.addEventListener("click", () => chooseCard(index));
    board.append(button);
  });
}

function chooseCard(index) {
  if (inputLocked) {
    return;
  }

  const button = getCardButton(index);
  const card = cards[index];

  if (!button || button.disabled || openCards.some((open) => open.index === index)) {
    return;
  }

  revealCard(index);
  openCards.push({ index, id: card.id });

  if (openCards.length < 2) {
    statusLabel.textContent = `${card.label}を見つけました。もう1枚を探してください`;
    return;
  }

  moves += 1;
  inputLocked = true;

  const [first, second] = openCards;

  if (first.id === second.id) {
    matchedPairs += 1;
    markMatched(first.index, second.index);
    feedPeach(second.index);
    openCards = [];
    statusLabel.textContent = `${card.label}のペアが桃に溶けました`;
    inputLocked = false;
    renderStats();
    renderGrowth();

    if (matchedPairs >= motifs.length) {
      completionTimer = setTimeout(finishGame, 520);
    }
    return;
  }

  misses += 1;
  ripeness = Math.max(40, ripeness - 7);
  statusLabel.textContent = "違う札です。桃の甘さが少しゆらぎました";
  renderStats();
  renderGrowth();
  setTimeout(() => {
    hideCard(first.index);
    hideCard(second.index);
    openCards = [];
    inputLocked = false;
  }, 720);
}

function revealCard(index) {
  const button = getCardButton(index);
  const card = cards[index];
  button.classList.add("is-open");
  button.setAttribute("aria-label", `${card.label}の札`);
}

function hideCard(index) {
  const button = getCardButton(index);
  button.classList.remove("is-open");
  button.setAttribute("aria-label", "桃の札");
}

function markMatched(firstIndex, secondIndex) {
  [firstIndex, secondIndex].forEach((index) => {
    const button = getCardButton(index);
    const card = cards[index];
    button.classList.add("is-matched");
    button.disabled = true;
    button.setAttribute("aria-label", `${card.label}のペア成立`);
  });
}

function feedPeach(cardIndex) {
  const button = getCardButton(cardIndex);
  const rect = button.getBoundingClientRect();
  const layerRect = juiceLayer.getBoundingClientRect();
  const tone = cards[cardIndex].tone;

  for (let i = 0; i < 8; i += 1) {
    const drop = document.createElement("span");
    drop.className = "juice-drop";
    drop.style.setProperty("--x", `${rect.left - layerRect.left + rect.width / 2 + randomBetween(-22, 22)}px`);
    drop.style.setProperty("--y", `${rect.top - layerRect.top + rect.height / 2 + randomBetween(-16, 16)}px`);
    drop.style.setProperty("--size", `${randomBetween(9, 22)}px`);
    drop.style.setProperty("--tone", tone);
    juiceLayer.append(drop);
    setTimeout(() => drop.remove(), 900);
  }

  peach.classList.remove("is-fed");
  peach.offsetWidth;
  peach.classList.add("is-fed");
}

function renderStats() {
  movesLabel.textContent = String(moves);
  missesLabel.textContent = String(misses);
  ripenessLabel.textContent = String(ripeness);
  ripenessFill.style.transform = `scaleX(${ripeness / 100})`;
}

function renderGrowth() {
  const stages = ["つぼみ", "小桃", "色づき", "完熟", "収穫"];
  const stage = Math.min(stages.length - 1, Math.floor(matchedPairs / 2));
  const isFed = peach.classList.contains("is-fed");
  peach.className = "peach";
  peach.classList.add(`stage-${stage}`);

  if (isFed) {
    peach.classList.add("is-fed");
  }

  if (matchedPairs === 0) {
    phaseLabel.textContent = stages[0];
  } else if (matchedPairs >= motifs.length) {
    phaseLabel.textContent = stages[4];
  } else {
    phaseLabel.textContent = stages[stage];
  }
}

function finishGame() {
  inputLocked = true;
  const score = calculateScore();
  saveBestScore(score);
  const rank = getRank(score, ripeness, misses);
  resultRank.textContent = rank.kicker;
  resultTitle.textContent = rank.title;
  resultDetail.textContent = `手数 ${moves} / ミス ${misses} / 熟度 ${ripeness} / 得点 ${score}`;
  result.classList.add("is-visible");
  result.setAttribute("aria-hidden", "false");
  statusLabel.textContent = `${rank.title}。もういちどで新しい桃園へ`;
}

function calculateScore() {
  const base = 1600;
  const moveBonus = Math.max(0, 560 - Math.max(0, moves - motifs.length) * 55);
  const ripenessBonus = ripeness * 12;
  const missPenalty = misses * 45;
  return Math.max(0, base + moveBonus + ripenessBonus - missPenalty);
}

function getRank(score, currentRipeness, currentMisses) {
  if (currentMisses === 0 && currentRipeness >= 95) {
    return { kicker: "幻の収穫", title: "一滴もこぼれない完熟桃" };
  }

  if (score >= 3000) {
    return { kicker: "上出来", title: "朝露で光る桃" };
  }

  if (currentRipeness >= 70) {
    return { kicker: "収穫", title: "よく熟した桃" };
  }

  return { kicker: "小さな収穫", title: "もう少し育てたい桃" };
}

function saveBestScore(score) {
  const best = loadBestScore();

  if (score > best) {
    localStorage.setItem(bestKey, String(score));
    bestScoreLabel.textContent = String(score);
  }
}

function loadBestScore() {
  return Number(localStorage.getItem(bestKey) || 0);
}

function getCardButton(index) {
  return board.querySelector(`[data-index="${index}"]`);
}

function shuffle(items) {
  const result = [...items];

  for (let index = result.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
  }

  return result;
}

function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}
