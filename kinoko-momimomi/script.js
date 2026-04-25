const mushroom = document.getElementById("mushroom");
const joyFill = document.getElementById("joy-fill");
const timeLeft = document.getElementById("time-left");
const scoreLabel = document.getElementById("score");
const bestScoreLabel = document.getElementById("best-score");
const message = document.getElementById("message");
const restartButton = document.getElementById("restart");
const floatingLayer = document.getElementById("floating-layer");

const totalTime = 20;
const bestKey = "kinoko-momimomi-best";

let score = 0;
let joy = 0;
let remaining = totalTime;
let playing = true;
let pointerDown = false;
let lastPoint = null;
let lastRubAt = 0;
let overload = 0;
let rafId = 0;

bestScoreLabel.textContent = String(loadBestScore());
render();
tick();

mushroom.addEventListener("pointerdown", (event) => {
  if (!playing) {
    return;
  }

  pointerDown = true;
  lastPoint = { x: event.clientX, y: event.clientY };
  mushroom.setPointerCapture(event.pointerId);
  rub(event.clientX, event.clientY, 1.2);
});

mushroom.addEventListener("pointermove", (event) => {
  if (!playing || !pointerDown || !lastPoint) {
    return;
  }

  const dx = event.clientX - lastPoint.x;
  const dy = event.clientY - lastPoint.y;
  const distance = Math.hypot(dx, dy);

  if (distance > 4) {
    const energy = Math.min(distance / 9, 4.2);
    rub(event.clientX, event.clientY, energy);
    mushroom.style.setProperty("--tilt", `${Math.max(-8, Math.min(8, dx * 0.18))}deg`);
    lastPoint = { x: event.clientX, y: event.clientY };
  }
});

mushroom.addEventListener("pointerup", endRub);
mushroom.addEventListener("pointercancel", endRub);
mushroom.addEventListener("click", (event) => {
  if (!playing) {
    return;
  }

  rub(event.clientX, event.clientY, 0.9);
});

restartButton.addEventListener("click", resetGame);

function rub(clientX, clientY, power) {
  const now = performance.now();
  const interval = now - lastRubAt;
  lastRubAt = now;

  const pacedBonus = interval > 35 && interval < 120 ? 1.35 : 1;
  const gain = Math.round(power * 10 * pacedBonus);
  const overloadGain = interval < 26 ? 14 : Math.max(0, power * 4 - 2);

  score += gain;
  joy = Math.min(100, joy + power * 5.5);
  overload = Math.min(100, overload + overloadGain);

  mushroom.classList.add("is-rubbing");
  clearTimeout(mushroom._rubTimer);
  mushroom._rubTimer = setTimeout(() => {
    mushroom.classList.remove("is-rubbing");
    mushroom.style.setProperty("--tilt", "0deg");
  }, 120);

  spawnFloat(clientX, clientY, interval < 26 ? "あつっ" : `+${gain}`);
  updateMood();
  render();
}

function endRub(event) {
  pointerDown = false;
  lastPoint = null;

  if (event?.pointerId !== undefined && mushroom.hasPointerCapture(event.pointerId)) {
    mushroom.releasePointerCapture(event.pointerId);
  }
}

function tick() {
  let previous = performance.now();

  const frame = (now) => {
    if (!playing) {
      return;
    }

    const delta = (now - previous) / 1000;
    previous = now;

    remaining = Math.max(0, remaining - delta);
    joy = Math.max(0, joy - delta * 6);
    overload = Math.max(0, overload - delta * 24);

    if (overload >= 85) {
      joy = Math.max(0, joy - delta * 36);
      score = Math.max(0, score - Math.ceil(delta * 60));
    }

    if (remaining === 0) {
      finishGame();
      return;
    }

    updateMood();
    render();

    rafId = requestAnimationFrame(frame);
  };

  rafId = requestAnimationFrame(frame);
}

function updateMood() {
  const overloadActive = overload >= 60;
  mushroom.classList.toggle("is-overload", overloadActive);

  if (!playing) {
    return;
  }

  if (overload >= 85) {
    message.textContent = "さわりすぎです。ちょっと優しく";
    return;
  }

  if (joy >= 80) {
    message.textContent = "きのこがごきげんです";
    return;
  }

  if (joy >= 45) {
    message.textContent = "いいリズムです";
    return;
  }

  message.textContent = "ドラッグか連打でモミモミ開始";
}

function render() {
  joyFill.style.width = `${joy}%`;
  timeLeft.textContent = remaining.toFixed(1);
  scoreLabel.textContent = String(score);
}

function finishGame() {
  playing = false;
  endRub();
  cancelAnimationFrame(rafId);

  const bestScore = loadBestScore();
  if (score > bestScore) {
    localStorage.setItem(bestKey, String(score));
    bestScoreLabel.textContent = String(score);
    message.textContent = `ベスト更新。${score} きのこポイント`;
  } else {
    message.textContent = `終了。${score} きのこポイント`;
  }
}

function resetGame() {
  cancelAnimationFrame(rafId);
  score = 0;
  joy = 0;
  remaining = totalTime;
  overload = 0;
  playing = true;
  pointerDown = false;
  lastPoint = null;
  lastRubAt = 0;
  floatingLayer.replaceChildren();
  mushroom.classList.remove("is-overload", "is-rubbing");
  message.textContent = "ドラッグか連打でモミモミ開始";
  render();
  tick();
}

function spawnFloat(clientX, clientY, text) {
  const stage = floatingLayer.getBoundingClientRect();
  const floatText = document.createElement("span");
  floatText.className = "float-text";
  floatText.textContent = text;
  floatText.style.left = `${clientX - stage.left}px`;
  floatText.style.top = `${clientY - stage.top}px`;
  floatingLayer.append(floatText);
  setTimeout(() => floatText.remove(), 700);
}

function loadBestScore() {
  return Number(localStorage.getItem(bestKey) || 0);
}
