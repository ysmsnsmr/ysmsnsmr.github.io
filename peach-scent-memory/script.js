const stage = document.getElementById("stage");
const peach = document.getElementById("peach");
const scentLayer = document.getElementById("scent-layer");
const memoryStrip = document.getElementById("memory-strip");
const scoreLabel = document.getElementById("score");
const roundLabel = document.getElementById("round");
const focusLabel = document.getElementById("focus");
const bestScoreLabel = document.getElementById("best-score");
const restartButton = document.getElementById("restart-button");
const phaseLabel = document.getElementById("phase-label");
const currentScentLabel = document.getElementById("current-scent");
const hintLabel = document.getElementById("hint");
const statusLabel = document.getElementById("status");
const floatingLayer = document.getElementById("floating-layer");
const prevScentButton = document.getElementById("prev-scent");
const nextScentButton = document.getElementById("next-scent");
const sniffButton = document.getElementById("sniff-button");

const bestKey = "peach-scent-memory-best";
const scents = [
  { name: "白桃", tone: "rgba(255, 207, 196, 0.74)", glow: "rgba(247, 163, 142, 0.48)", glyph: "○" },
  { name: "雨", tone: "rgba(183, 210, 218, 0.7)", glow: "rgba(117, 157, 171, 0.42)", glyph: "しずく" },
  { name: "葉", tone: "rgba(137, 177, 122, 0.72)", glow: "rgba(85, 128, 86, 0.38)", glyph: "葉" },
  { name: "砂糖", tone: "rgba(255, 245, 214, 0.82)", glow: "rgba(215, 176, 99, 0.42)", glyph: "きら" },
  { name: "産毛", tone: "rgba(235, 203, 178, 0.72)", glow: "rgba(203, 146, 111, 0.38)", glyph: "ふわ" },
  { name: "夕暮れ", tone: "rgba(214, 127, 132, 0.62)", glow: "rgba(195, 87, 104, 0.38)", glyph: "夕" },
  { name: "蜜", tone: "rgba(232, 178, 83, 0.72)", glow: "rgba(194, 137, 46, 0.42)", glyph: "蜜" }
];

let score = 0;
let round = 1;
let focus = 100;
let sequence = [];
let answerIndex = 0;
let currentLayerIndex = 0;
let phase = "memorize";
let memoryTimers = [];

bestScoreLabel.textContent = String(loadBestScore());
startRound();

stage.addEventListener("pointerdown", onSniff);
restartButton.addEventListener("click", resetGame);
prevScentButton.addEventListener("click", () => shiftScent(-1));
nextScentButton.addEventListener("click", () => shiftScent(1));
sniffButton.addEventListener("click", () => {
  const center = getStageCenter();
  sniffCurrent(center.x, center.y);
});

function startRound() {
  clearMemoryTimers();
  phase = "memorize";
  answerIndex = 0;
  currentLayerIndex = 0;
  sequence = buildSequence(Math.min(7, round + 2));
  stage.classList.remove("is-complete", "is-wrong");
  stage.classList.add("is-memorizing");
  phaseLabel.textContent = "記憶";
  currentScentLabel.textContent = "桃";
  hintLabel.textContent = "桃から現れる香りの順を覚えてください";
  statusLabel.textContent = "香り札を見届けたら、ボタンで香り名を表示して同じ順に嗅ぎます。";
  renderMemoryStrip();
  renderScentField(sequence[0]);
  render();
  playMemorySequence();
}

function playMemorySequence() {
  sequence.forEach((scentIndex, index) => {
    const showTimer = setTimeout(() => {
      const scent = scents[scentIndex];
      peach.classList.add("is-glowing");
      currentScentLabel.textContent = scent.name;
      hintLabel.textContent = `${index + 1}番目の香り`;
      renderMemoryStrip(index, index);
      renderScentField(scentIndex);
    }, 720 + index * 920);

    const hideTimer = setTimeout(() => {
      peach.classList.remove("is-glowing");
    }, 1230 + index * 920);

    memoryTimers.push(showTimer, hideTimer);
  });

  const finishTimer = setTimeout(() => {
    phase = "search";
    stage.classList.remove("is-memorizing");
    phaseLabel.textContent = "探索";
    currentLayerIndex = 0;
    hintLabel.textContent = "ボタンで香り名をめくり、タップで嗅ぐ";
    statusLabel.textContent = "香りをめくって候補を表示し、合っていると思ったら嗅いでください。";
    renderScentField(currentLayerIndex);
    renderMemoryStrip();
    render();
  }, 1000 + sequence.length * 920);

  memoryTimers.push(finishTimer);
}

function shiftScent(direction) {
  if (phase !== "search") {
    return;
  }

  currentLayerIndex = (currentLayerIndex + direction + scents.length) % scents.length;
  renderScentField(currentLayerIndex);
  statusLabel.textContent = `${scents[currentLayerIndex].name}を表示しました。合っていると思ったら嗅いでください。`;
  render();
}

function onSniff(event) {
  sniffCurrent(event.clientX, event.clientY);
}

function sniffCurrent(clientX, clientY) {
  if (phase === "memorize") {
    spawnFloating(clientX, clientY, "まだ記憶");
    return;
  }

  if (phase === "complete" || phase === "over") {
    resetGame();
    return;
  }

  const expected = sequence[answerIndex];
  const actual = currentLayerIndex;

  if (actual === expected) {
    const gained = 120 + round * 18 + answerIndex * 12 + Math.round(focus * 0.6);
    score += gained;
    spawnFloating(clientX, clientY, `+${gained} ${scents[actual].name}`);
    answerIndex += 1;
    statusLabel.textContent = answerIndex >= sequence.length
      ? "香りを一帖ぶん結びました。"
      : `正解。次は${answerIndex + 1}番目の香りです。`;

    if (answerIndex >= sequence.length) {
      finishRound();
    }
  } else {
    focus = Math.max(0, focus - 18);
    stage.classList.remove("is-wrong");
    stage.offsetWidth;
    stage.classList.add("is-wrong");
    spawnFloating(clientX, clientY, "霞んだ");
    statusLabel.textContent = `${scents[actual].name}ではありません。記憶が少し霞みました。`;

    if (focus <= 0) {
      endGame();
    }
  }

  renderMemoryStrip();
  render();
}

function finishRound() {
  phase = "complete";
  stage.classList.add("is-complete");
  phaseLabel.textContent = "結香";
  currentScentLabel.textContent = "満ちる";
  hintLabel.textContent = "次の香り帖へ移ります";
  score += round * 90;
  focus = Math.min(100, focus + 9);
  saveBestScore();
  render();

  const timer = setTimeout(() => {
    round += 1;
    startRound();
  }, 1600);
  memoryTimers.push(timer);
}

function endGame() {
  phase = "over";
  clearMemoryTimers();
  stage.classList.remove("is-memorizing");
  phaseLabel.textContent = "散香";
  currentScentLabel.textContent = "霞";
  hintLabel.textContent = "タップで再挑戦";
  statusLabel.textContent = `香りは霞に戻りました。得点 ${score}`;
  saveBestScore();
  render();
}

function resetGame() {
  clearMemoryTimers();
  score = 0;
  round = 1;
  focus = 100;
  sequence = [];
  answerIndex = 0;
  currentLayerIndex = 0;
  startRound();
}

function buildSequence(length) {
  const result = [];
  let previous = -1;

  for (let i = 0; i < length; i += 1) {
    let next = Math.floor(Math.random() * scents.length);

    if (next === previous) {
      next = (next + 1 + Math.floor(Math.random() * (scents.length - 1))) % scents.length;
    }

    result.push(next);
    previous = next;
  }

  return result;
}

function render() {
  scoreLabel.textContent = String(score);
  roundLabel.textContent = String(round);
  focusLabel.textContent = String(focus);
  renderControls();

  if (phase === "search") {
    const scent = scents[currentLayerIndex];
    phaseLabel.textContent = "探索";
    currentScentLabel.textContent = scent.name;
    scentLayer.style.setProperty("--drift", `${(currentLayerIndex - 3) * -10}px`);
  }
}

function renderControls() {
  const canChoose = phase === "search";
  prevScentButton.disabled = !canChoose;
  nextScentButton.disabled = !canChoose;
  sniffButton.disabled = !canChoose;
}

function renderMemoryStrip(revealThrough = -1, activeIndex = -1) {
  memoryStrip.replaceChildren();

  sequence.forEach((scentIndex, index) => {
    const scent = scents[scentIndex];
    const isAnswered = index < answerIndex;
    const shouldReveal = index <= revealThrough || isAnswered;
    const card = document.createElement("span");
    card.className = "memory-card";
    card.textContent = shouldReveal ? scent.name : String(index + 1);
    card.style.setProperty("--card-tone", scent.tone);

    if (shouldReveal) {
      card.classList.add("is-revealed");
    }

    if (!shouldReveal) {
      card.classList.add("is-pending");
    }

    if (isAnswered) {
      card.classList.add("is-done");
    }

    if (index === activeIndex || index === answerIndex && phase === "search") {
      card.classList.add("is-current");
    }

    memoryStrip.append(card);
  });
}

function renderScentField(scentIndex) {
  const scent = scents[scentIndex];
  scentLayer.replaceChildren();

  for (let i = 0; i < 22; i += 1) {
    const mote = document.createElement("span");
    mote.className = "scent";
    mote.style.setProperty("--x", `${randomBetween(12, 88)}%`);
    mote.style.setProperty("--y", `${randomBetween(8, 88)}%`);
    mote.style.setProperty("--size", `${randomBetween(14, 58)}px`);
    mote.style.setProperty("--rot", `${randomBetween(-60, 60)}deg`);
    mote.style.setProperty("--alpha", `${randomBetween(0.18, 0.72)}`);
    mote.style.setProperty("--speed", `${randomBetween(1.8, 4.4)}s`);
    mote.style.setProperty("--tone", scent.tone);
    mote.style.setProperty("--glow", scent.glow);
    scentLayer.append(mote);
  }
}

function spawnFloating(clientX, clientY, text) {
  const rect = floatingLayer.getBoundingClientRect();
  const floatText = document.createElement("span");
  floatText.className = "float-text";
  floatText.textContent = text;
  floatText.style.left = `${clientX - rect.left}px`;
  floatText.style.top = `${clientY - rect.top}px`;
  floatingLayer.append(floatText);
  setTimeout(() => floatText.remove(), 900);
}

function getStageCenter() {
  const rect = stage.getBoundingClientRect();
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2
  };
}

function saveBestScore() {
  const best = loadBestScore();

  if (score > best) {
    localStorage.setItem(bestKey, String(score));
    bestScoreLabel.textContent = String(score);
  }
}

function loadBestScore() {
  return Number(localStorage.getItem(bestKey) || 0);
}

function clearMemoryTimers() {
  memoryTimers.forEach((timer) => clearTimeout(timer));
  memoryTimers = [];
}

function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}
