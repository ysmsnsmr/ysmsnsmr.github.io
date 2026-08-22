import { createServer } from "node:http";
import { promises as fs } from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const require = createRequire(import.meta.url);
const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fixtureRoot = path.join(repositoryRoot, "scripts/fixtures/meta_ads_tracker");
const fixtureNames = [
  "empty-week",
  "normal-week",
  "high-priority",
  "long-and-unknown-dates",
  "filtered-no-results"
];
const viewports = [
  { name: "mobile", width: 375, height: 667 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "desktop", width: 1440, height: 900 }
];
const fixtures = new Map(
  await Promise.all(
    fixtureNames.map(async (name) => [
      name,
      JSON.parse(await fs.readFile(path.join(fixtureRoot, `${name}.json`), "utf8"))
    ])
  )
);
const axeSource = await fs.readFile(require.resolve("axe-core/axe.min.js"), "utf8");
const artifactDirectory = process.env.META_ADS_UI_ARTIFACT_DIR
  ? path.resolve(process.env.META_ADS_UI_ARTIFACT_DIR)
  : null;
if (artifactDirectory) await fs.mkdir(artifactDirectory, { recursive: true });

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function isInside(root, candidate) {
  return candidate === root || candidate.startsWith(`${root}${path.sep}`);
}

function reportFor(fixture) {
  return {
    schemaVersion: "meta-ads-weekly-index/v1",
    generatedAt: "2026-08-21T10:00:00Z",
    week: fixture.week,
    filters: fixture.filters,
    items: fixture.items
  };
}

async function startServer() {
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url || "/", "http://127.0.0.1");
      if (url.pathname === "/meta-ads-updates/latest.json") {
        const referer = new URL(request.headers.referer || "http://127.0.0.1/?fixture=normal-week");
        const fixtureName = referer.searchParams.get("fixture") || "normal-week";
        const fixture = fixtures.get(fixtureName);
        if (!fixture) return response.writeHead(404).end("Unknown fixture");
        response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
        return response.end(JSON.stringify(reportFor(fixture)));
      }
      if (url.pathname === "/meta-ads-updates/secondary-beta.json") {
        const referer = new URL(request.headers.referer || "http://127.0.0.1/");
        if (referer.searchParams.get("secondaryStatus") === "invalid") {
          response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
          return response.end(JSON.stringify({ schemaVersion: "meta-ads-secondary-beta-status/v1", signals: [{ title: "must not render" }] }));
        }
      }
      let filePath = path.resolve(repositoryRoot, `.${decodeURIComponent(url.pathname)}`);
      if (!isInside(repositoryRoot, filePath)) return response.writeHead(403).end("Forbidden");
      const stat = await fs.stat(filePath).catch(() => null);
      if (stat?.isDirectory()) filePath = path.join(filePath, "index.html");
      const mime = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json" }[path.extname(filePath)] || "application/octet-stream";
      response.writeHead(200, { "content-type": `${mime}; charset=utf-8` });
      response.end(await fs.readFile(filePath));
    } catch {
      response.writeHead(404).end("Not found");
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  assert(address && typeof address !== "string", "Could not start UI test server");
  return {
    origin: `http://127.0.0.1:${address.port}`,
    close: () => new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
  };
}

async function applyFixtureFilters(page, fixture) {
  if (fixture.filters.sourceId !== "all") await page.selectOption("#source-filter", fixture.filters.sourceId);
  if (fixture.filters.priority !== "all") await page.selectOption("#priority-filter", fixture.filters.priority);
  if (fixture.filters.query) await page.fill("#query-filter", fixture.filters.query);
}

async function assertTokens(page) {
  const values = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const masthead = getComputedStyle(document.querySelector(".masthead"));
    const panel = getComputedStyle(document.querySelector(".control-panel"));
    const betaStatus = getComputedStyle(document.querySelector("#secondary-beta-status"));
    return {
      canvas: root.getPropertyValue("--tracker-canvas").trim(),
      blue: root.getPropertyValue("--tracker-blue").trim(),
      radius: root.getPropertyValue("--tracker-radius-md").trim(),
      target: root.getPropertyValue("--tracker-target-min").trim(),
      mastheadDisplay: masthead.display,
      mastheadBorder: masthead.borderBottomStyle,
      panelRadius: panel.borderRadius,
      betaRadius: betaStatus.borderRadius,
      betaBorder: betaStatus.borderTopStyle,
      betaMargin: betaStatus.marginTop
    };
  });
  assert(JSON.stringify(values) === JSON.stringify({
    canvas: "#f5f7fb",
    blue: "#1967d2",
    radius: "10px",
    target: "44px",
    mastheadDisplay: "grid",
    mastheadBorder: "solid",
    panelRadius: "10px",
    betaRadius: "10px",
    betaBorder: "solid",
    betaMargin: "16px"
  }), `Approved Workbench token/layout mismatch: ${JSON.stringify(values)}`);
}

async function assertAccessibilityAndLayout(page, label) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert(overflow <= 1, `${label}: horizontal overflow ${overflow}px`);
  const undersized = await page.locator("button, select, input, .source-link").evaluateAll((nodes) =>
    nodes.map((node) => ({ text: node.textContent || node.getAttribute("placeholder"), rect: node.getBoundingClientRect() }))
      .filter(({ rect }) => rect.width > 0 && rect.height > 0 && (rect.height < 44 || rect.width < 44))
      .map(({ text, rect }) => `${text}:${rect.width}x${rect.height}`)
  );
  assert(undersized.length === 0, `${label}: controls below 44px: ${undersized.join(", ")}`);
  await page.locator("body").click({ position: { x: 1, y: 1 } });
  await page.keyboard.press("Tab");
  const focus = await page.evaluate(() => {
    const active = document.activeElement;
    const style = getComputedStyle(active);
    return { id: active?.id, outline: style.outlineStyle, width: style.outlineWidth };
  });
  assert(focus.id === "source-filter" && focus.outline !== "none" && focus.width === "3px", `${label}: keyboard focus is not visibly styled`);
  await page.addScriptTag({ content: axeSource });
  const axe = await page.evaluate(async () => globalThis.axe.run(document, { runOnly: ["wcag2a", "wcag2aa"] }));
  assert(axe.violations.length === 0, `${label}: axe violations: ${axe.violations.map((item) => item.id).join(", ")}`);
}

const server = await startServer();
const browser = await chromium.launch({ headless: true });
let caseCount = 0;
try {
  for (const fixtureName of fixtureNames) {
    const fixture = fixtures.get(fixtureName);
    for (const viewport of viewports) {
      const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
      const consoleErrors = [];
      const pageErrors = [];
      page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
      page.on("pageerror", (error) => pageErrors.push(error.message));
      const label = `${fixtureName}/${viewport.name}`;
      await page.goto(`${server.origin}/meta-ads-updates/index.html?fixture=${fixtureName}`, { waitUntil: "networkidle" });
      await applyFixtureFilters(page, fixture);
      const expectedCount = fixtureName === "filtered-no-results" ? 0 : fixture.items.length;
      assert(await page.locator("#update-list .update-card").count() === expectedCount, `${label}: unexpected card count`);
      if (expectedCount === 0) assert(await page.locator("#empty-state").isVisible(), `${label}: empty state is missing`);
      assert(await page.locator("#secondary-beta-status-title").innerText() === "Gate B：証跡不足", `${label}: Secondary β must reflect the current Gate B BLOCK status`);
      assert((await page.locator("#secondary-beta-status-copy").innerText()).includes("Secondary βを進めません"), `${label}: Secondary β boundary copy is missing`);
      assert((await page.locator(".secondary-empty").innerText()).includes("この公開UI・公式候補データ・週次indexには追加しません"), `${label}: Secondary signals must remain outside public and official paths`);
      assert(consoleErrors.length === 0 && pageErrors.length === 0, `${label}: runtime errors: ${[...consoleErrors, ...pageErrors].join("; ")}`);
      await assertTokens(page);
      await assertAccessibilityAndLayout(page, label);
      if (artifactDirectory) {
        await page.screenshot({ path: path.join(artifactDirectory, `${fixtureName}-${viewport.name}-viewport.png`) });
        await page.screenshot({ path: path.join(artifactDirectory, `${fixtureName}-${viewport.name}-full-page.png`), fullPage: true });
      }
      await page.close();
      caseCount += 1;
    }
  }

  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(`${server.origin}/meta-ads-updates/index.html?fixture=normal-week`, { waitUntil: "networkidle" });
  assert(await page.locator("#update-list .update-card").count() === 3, "normal-week initial count must be three");
  await page.selectOption("#source-filter", "meta-business-sdk-releases");
  assert(await page.locator("#update-list .update-card").count() === 1, "source filter failed");
  await page.selectOption("#priority-filter", "high");
  assert(await page.locator("#update-list .update-card").count() === 0, "combined filter failed");
  await page.click("#reset-button");
  assert(await page.locator("#update-list .update-card").count() === 3, "reset failed");
  await page.fill("#query-filter", "設定手順B");
  assert(await page.locator("#update-list .update-card").count() === 1, "query filter failed");
  await page.goto(`${server.origin}/meta-ads-updates/index.html?fixture=normal-week&secondaryStatus=invalid`, { waitUntil: "networkidle" });
  assert(await page.locator("#secondary-beta-status-title").innerText() === "Secondary βの状態を表示できません", "Malformed Secondary β status must fail closed");
  assert(!(await page.locator(".secondary-beta").innerText()).includes("must not render"), "Malformed Secondary β data must not be displayed");
  await page.close();
  console.log(`PASS: production UI ${caseCount}/15 viewport cases, interactions, overflow, targets, focus, axe, and approved tokens`);
} finally {
  await browser.close();
  await server.close();
}
