const stage = document.getElementById("stage");
const tapZone = document.getElementById("tap-zone");
const tapLabel = document.getElementById("tap-label");
const jar = document.getElementById("jar");
const orangeLayer = document.getElementById("orange-layer");
const floatLayer = document.getElementById("float-layer");
const scoreLabel = document.getElementById("score");
const bestScoreLabel = document.getElementById("best-score");
const timeLeftLabel = document.getElementById("time-left");
const pressureFill = document.getElementById("pressure-fill");
const fillGauge = document.getElementById("fill-gauge");
const juiceFill = document.getElementById("juice-fill");
const statusLabel = document.getElementById("status");
const restartButton = document.getElementById("restart-button");
const soundButton = document.getElementById("sound-button");

const totalTime = 35;
const maxOranges = 32;
const bestKey = "orange-bottle-best";
const speechProfiles = [
  { name: "kid-bright", text: "イケる！", pitch: 1.65, rate: 1.14, volume: 0.95 },
  { name: "kid-calm", text: "イケる！", pitch: 1.35, rate: 0.98, volume: 0.9 },
  { name: "adult-woman", text: "イケる！", pitch: 1.08, rate: 0.96, volume: 0.95 },
  { name: "adult-man", text: "イケる！", pitch: 0.78, rate: 0.9, volume: 0.95 },
  { name: "elder-woman", text: "イケる！", pitch: 0.88, rate: 0.72, volume: 0.92 },
  { name: "elder-man", text: "イケる！", pitch: 0.58, rate: 0.76, volume: 0.92 },
  { name: "cheer", text: "イケるー！", pitch: 1.22, rate: 1.2, volume: 1 }
];

let score = 0;
let pressure = 0;
let fill = 0;
let remaining = totalTime;
let oranges = 0;
let combo = 0;
let playing = true;
let started = false;
let voiceEnabled = true;
let cracked = false;
let lastTapAt = 0;
let endedAt = 0;
let rafId = 0;
let previousFrameAt = 0;
let voices = [];

bestScoreLabel.textContent = String(loadBestScore());
render();
requestAnimationFrame(loop);

if ("speechSynthesis" in window) {
  voices = window.speechSynthesis.getVoices();
  window.speechSynthesis.addEventListener("voiceschanged", () => {
    voices = window.speechSynthesis.getVoices();
  });
}

tapZone.addEventListener("pointerdown", (event) => {
  event.preventDefault();
  squeezeOrange(event.clientX, event.clientY);
});

restartButton.addEventListener("click", resetGame);

soundButton.addEventListener("click", () => {
  voiceEnabled = !voiceEnabled;
  soundButton.setAttribute("aria-pressed", String(voiceEnabled));
  soundButton.textContent = voiceEnabled ? "VOICE ON" : "VOICE OFF";
});

function loop(now) {
  if (!previousFrameAt) {
    previousFrameAt = now;
  }

  const delta = Math.min(0.05, (now - previousFrameAt) / 1000);
  previousFrameAt = now;

  if (playing && started) {
    remaining = Math.max(0, remaining - delta);
    pressure = Math.max(0, pressure - delta * (pressure > 72 ? 16 : 9));

    if (pressure > 92) {
      score = Math.max(0, score - Math.ceil(delta * 80));
    }

    if (remaining <= 0) {
      endGame(fill >= 94 ? "FULL BOTTLE" : "TIME UP", false);
    }
  }

  animateTarget(now);
  render();
  rafId = requestAnimationFrame(loop);
}

function squeezeOrange(clientX, clientY) {
  if (!playing) {
    if (performance.now() - endedAt > 700) {
      resetGame();
    }
    return;
  }

  const now = performance.now();
  const interval = lastTapAt ? now - lastTapAt : 720;
  lastTapAt = now;
  started = true;

  const sweetSpot = getSweetSpot(now);
  const stageRect = stage.getBoundingClientRect();
  const xRatio = clamp((clientX - stageRect.left) / stageRect.width, 0, 1);
  const aim = 1 - Math.abs(xRatio - sweetSpot) * 1.8;
  const aimBonus = clamp(aim, 0.32, 1.22);
  const panic = interval < 190 ? 23 : interval < 310 ? 15 : interval < 520 ? 8 : 3;
  const breathBonus = interval > 340 && interval < 840 ? 1.28 : 1;
  const pressurePenalty = pressure > 70 ? 0.62 : pressure > 52 ? 0.82 : 1;
  const gained = Math.max(6, Math.round(14 * aimBonus * breathBonus * pressurePenalty + combo * 0.8));

  pressure = clamp(pressure + panic + oranges * 0.24, 0, 120);
  combo = interval > 280 && interval < 980 ? Math.min(combo + 1, 18) : 0;
  score += gained;

  if (pressure >= 100) {
    spawnFloating(clientX, clientY, "パンッ");
    speakIkeru(true);
    endGame("TOO MUCH", true);
    return;
  }

  addOrange(aimBonus, pressure);
  fill = clamp(fill + (2.4 + aimBonus * 1.65) * pressurePenalty, 0, 100);
  spawnFloating(clientX, clientY, `+${gained}`);
  speakIkeru(false);
  pulseJar(interval < 260);
  updateStatus(interval, aimBonus);

  if (fill >= 100 || oranges >= maxOranges) {
    endGame("SEALED", false);
  }
}

function addOrange(aimBonus, currentPressure) {
  oranges += 1;

  const orange = document.createElement("span");
  const row = Math.floor((oranges - 1) / 5);
  const slot = (oranges - 1) % 5;
  const x = 18 + slot * 16 + randomBetween(-5, 5) + (row % 2) * 6;
  const y = 4 + row * 9.5 + randomBetween(-2.2, 2.8);
  const size = clamp(44 - row * 1.8 + randomBetween(-3, 4), 26, 46);
  const squeezeScale = clamp(1 - currentPressure / 340, 0.72, 1);
  const rot = randomBetween(-34, 34);
  const spin = randomBetween(0, 180);

  orange.className = "orange";
  orange.style.setProperty("--x", `${clamp(x, 15, 85)}%`);
  orange.style.setProperty("--y", `${clamp(y, 3, 86)}%`);
  orange.style.setProperty("--size", `${size}px`);
  orange.style.setProperty("--scale", `${squeezeScale * (0.88 + aimBonus * 0.12)}`);
  orange.style.setProperty("--rot", `${rot}deg`);
  orange.style.setProperty("--spin", `${spin}deg`);
  orangeLayer.append(orange);

  if (orangeLayer.children.length > maxOranges) {
    orangeLayer.firstElementChild.remove();
  }
}

function speakIkeru(isFinal) {
  if (!voiceEnabled || !("speechSynthesis" in window)) {
    return;
  }

  const profile = isFinal ? speechProfiles[5] : speechProfiles[Math.floor(Math.random() * speechProfiles.length)];
  const utterance = new SpeechSynthesisUtterance(profile.text);
  const japaneseVoices = voices.filter((voice) => /^ja\b|ja-JP/i.test(voice.lang));

  if (japaneseVoices.length) {
    utterance.voice = japaneseVoices[Math.floor(Math.random() * japaneseVoices.length)];
  }

  utterance.lang = "ja-JP";
  utterance.pitch = profile.pitch;
  utterance.rate = profile.rate;
  utterance.volume = profile.volume;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function updateStatus(interval, aimBonus) {
  if (pressure > 82) {
    statusLabel.textContent = "CRACKING";
    tapLabel.textContent = "WAIT";
    return;
  }

  if (interval < 260) {
    statusLabel.textContent = "HOT";
    tapLabel.textContent = "SLOW";
    return;
  }

  if (aimBonus > 1.05) {
    statusLabel.textContent = "CENTER";
    tapLabel.textContent = "TAP";
    return;
  }

  statusLabel.textContent = combo >= 6 ? "COMBO" : "PACKING";
  tapLabel.textContent = "TAP";
}

function endGame(reason, didCrack) {
  playing = false;
  cracked = didCrack;
  endedAt = performance.now();
  stage.classList.toggle("is-game-over", didCrack);
  jar.classList.toggle("is-danger", didCrack);
  tapLabel.textContent = "RETRY";
  statusLabel.textContent = reason;

  const bottleBonus = Math.round(fill * 7);
  score += bottleBonus;

  const bestScore = loadBestScore();
  if (score > bestScore) {
    localStorage.setItem(bestKey, String(score));
    bestScoreLabel.textContent = String(score);
  }

  render();
}

function resetGame() {
  score = 0;
  pressure = 0;
  fill = 0;
  remaining = totalTime;
  oranges = 0;
  combo = 0;
  playing = true;
  started = false;
  cracked = false;
  lastTapAt = 0;
  endedAt = 0;
  previousFrameAt = performance.now();
  orangeLayer.replaceChildren();
  floatLayer.replaceChildren();
  jar.classList.remove("is-danger");
  stage.classList.remove("is-game-over");
  tapLabel.textContent = "TAP";
  statusLabel.textContent = "READY";
  render();
}

function render() {
  scoreLabel.textContent = String(score);
  timeLeftLabel.textContent = remaining.toFixed(1);
  pressureFill.style.width = `${clamp(pressure, 0, 100)}%`;
  fillGauge.style.width = `${fill}%`;
  juiceFill.style.height = `${Math.min(fill * 0.78, 78)}%`;
  jar.classList.toggle("is-danger", pressure > 82 || cracked);
}

function animateTarget(now) {
  const ring = document.getElementById("target-ring");
  const sweetSpot = getSweetSpot(now);
  ring.style.left = `${26 + sweetSpot * 48}%`;
}

function getSweetSpot(now) {
  return 0.5 + Math.sin(now / 950) * 0.32;
}

function pulseJar(hard) {
  jar.style.setProperty("--shake", hard ? `${randomBetween(-7, 7)}px` : `${randomBetween(-3, 3)}px`);
  window.setTimeout(() => {
    jar.style.setProperty("--shake", "0px");
  }, 80);
}

function spawnFloating(clientX, clientY, text) {
  const rect = floatLayer.getBoundingClientRect();
  const span = document.createElement("span");
  span.className = "float-text";
  span.textContent = text;
  span.style.setProperty("--left", `${clientX - rect.left}px`);
  span.style.setProperty("--top", `${clientY - rect.top}px`);
  floatLayer.append(span);
  window.setTimeout(() => span.remove(), 780);
}

function loadBestScore() {
  return Number(localStorage.getItem(bestKey) || 0);
}

function randomBetween(min, max) {
  return min + Math.random() * (max - min);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
