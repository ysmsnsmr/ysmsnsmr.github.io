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
const demoReport = JSON.parse(await fs.readFile(path.join(repositoryRoot, "meta-ads-updates/demo-latest.json"), "utf8"));
const personalFeedReport = JSON.parse(await fs.readFile(path.join(repositoryRoot, "meta-ads-updates/personal-feed.json"), "utf8"));
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

function delayedRecoveryReportFor(fixture) {
  return {
    ...reportFor(fixture),
    schemaVersion: "meta-ads-weekly-index/v2",
    publication: {
      mode: "delayed_recovery",
      label: "遅延回復データ",
      recoveryHash: "a".repeat(64),
      recoveryGeneratedAt: "2026-08-29T03:03:02Z",
      cutoffAt: "2026-08-28T09:00:00Z",
      missingPreCutoffDates: ["2026-08-28"]
    }
  };
}

function personalFeedFixture() {
  const sources = [
    { id: "meta-product-news-rss", name: "Meta Newsroom Product News", classification: "official", sourceUrl: "https://about.fb.com/news/category/product-news/", platforms: ["Metaプラットフォーム全般"] },
    { id: "search-engine-land-meta-rss", name: "Search Engine Land (Meta / PPC)", classification: "unofficial", sourceUrl: "https://searchengineland.com/library/platforms/meta", platforms: ["Meta Ads"] }
  ];
  return {
    schemaVersion: "meta-ads-personal-feed/v1",
    generatedAt: "2026-08-29T09:00:00Z",
    sources,
    items: [
      { id: "meta-product-news-rss-aaaaaaaaaaaaaaaaaaaa", sourceId: "meta-product-news-rss", title: "Meta公式の製品更新", url: "https://about.fb.com/news/2026/08/product-update/", publishedDate: "2026-08-29", updatedDate: null, firstObservedAt: "2026-08-29T09:00:00Z", lastObservedAt: "2026-08-29T09:00:00Z", platforms: ["Metaプラットフォーム全般"], matchEvidence: [] },
      { id: "search-engine-land-meta-rss-bbbbbbbbbbbbbbbbbbbb", sourceId: "search-engine-land-meta-rss", title: "Meta Ads APIの観測記事", url: "https://searchengineland.com/meta-ads-api/", publishedDate: "2026-08-28", updatedDate: "2026-08-29", firstObservedAt: "2026-08-29T09:00:00Z", lastObservedAt: "2026-08-29T09:00:00Z", platforms: ["Meta Ads"], matchEvidence: ["category:PPC"] },
      { id: "search-engine-land-meta-rss-cccccccccccccccccccc", sourceId: "search-engine-land-meta-rss", title: "Meta Adsの表示変更", url: "https://searchengineland.com/meta-ads-ui/", publishedDate: null, updatedDate: null, firstObservedAt: "2026-08-29T09:00:00Z", lastObservedAt: "2026-08-29T09:00:00Z", platforms: ["Meta Ads"], matchEvidence: ["category:PPC"] }
    ]
  };
}

async function startServer() {
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url || "/", "http://127.0.0.1");
      if (url.pathname === "/meta-ads-updates/latest.json") {
        const referer = new URL(request.headers.referer || "http://127.0.0.1/");
        const fixtureName = referer.searchParams.get("fixture");
        if (fixtureName) {
          if (fixtureName === "delayed-recovery") {
            response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
            return response.end(JSON.stringify(delayedRecoveryReportFor(fixtures.get("normal-week"))));
          }
          const fixture = fixtures.get(fixtureName);
          if (!fixture) return response.writeHead(404).end("Unknown fixture");
          response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
          return response.end(JSON.stringify(reportFor(fixture)));
        }
      }
      if (url.pathname === "/meta-ads-updates/personal-feed.json") {
        const referer = new URL(request.headers.referer || "http://127.0.0.1/");
        if (referer.searchParams.get("personal-fixture") === "1") {
          response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
          return response.end(JSON.stringify(personalFeedFixture()));
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
    return {
      canvas: root.getPropertyValue("--tracker-canvas").trim(),
      blue: root.getPropertyValue("--tracker-blue").trim(),
      radius: root.getPropertyValue("--tracker-radius-md").trim(),
      target: root.getPropertyValue("--tracker-target-min").trim(),
      mastheadDisplay: masthead.display,
      mastheadBorder: masthead.borderBottomStyle,
      panelRadius: panel.borderRadius
    };
  });
  assert(JSON.stringify(values) === JSON.stringify({
    canvas: "#f5f7fb",
    blue: "#1967d2",
    radius: "10px",
    target: "44px",
    mastheadDisplay: "grid",
    mastheadBorder: "solid",
    panelRadius: "10px"
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

  const productionPage = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await productionPage.goto(`${server.origin}/meta-ads-updates/index.html`, { waitUntil: "networkidle" });
  assert(await productionPage.locator("#update-list .update-card").count() === personalFeedReport.items.length, "production route did not read personal-feed.json");
  assert(!(await productionPage.locator("#demo-banner").isVisible()), "production route must not show the demo banner");
  assert(!(await productionPage.locator("#recovery-banner").isVisible()), "ordinary production route must not show the delayed-recovery banner");
  assert(await productionPage.locator("#unofficial-notice").isVisible(), "Personal Feed must show the non-official-source notice");
  await productionPage.close();

  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    const label = `personal-feed/${viewport.name}`;
    await page.goto(`${server.origin}/meta-ads-updates/index.html?personal-fixture=1`, { waitUntil: "networkidle" });
    assert(await page.locator("#unofficial-notice").isVisible(), `${label}: non-official notice is missing`);
    assert(await page.locator("#update-list .update-card").count() === 3, `${label}: personal feed cards are missing`);
    assert(await page.locator(".origin-label--official").count() === 1, `${label}: official badge is missing`);
    assert(await page.locator(".origin-label--unofficial").count() === 2, `${label}: non-official badge is missing`);
    assert(await page.locator(".unofficial-copy").count() === 0, `${label}: per-card non-official warning must not be rendered`);
    assert((await page.locator(".fact-label").allTextContents()).filter((label) => label === "最終更新日").length === 3, `${label}: final update date label is missing`);
    assert(await page.locator(".masthead").textContent().then((text) => !text.includes("Personal information feed") && !text.includes("個人・同僚向けフィード")), `${label}: removed personal-feed copy is still visible`);
    const personalColumns = await page.locator("#update-list").evaluate((node) => getComputedStyle(node).gridTemplateColumns.trim().split(/\s+/).length);
    const expectedColumns = viewport.name === "desktop" ? 3 : viewport.name === "tablet" ? 2 : 1;
    assert(personalColumns === expectedColumns, `${label}: expected ${expectedColumns} personal-feed column(s), found ${personalColumns}`);
    assert(await page.locator(".source-link").evaluateAll((links) => links.every((link) => link.href.startsWith("https://") && link.target === "_blank" && link.rel.includes("noreferrer"))), `${label}: source links are unsafe`);
    assert(consoleErrors.length === 0 && pageErrors.length === 0, `${label}: runtime errors: ${[...consoleErrors, ...pageErrors].join("; ")}`);
    await assertTokens(page);
    await assertAccessibilityAndLayout(page, label);
    if (viewport.name === "desktop") {
      await page.selectOption("#priority-filter", "unofficial");
      assert(await page.locator("#update-list .update-card").count() === 2, "personal feed non-official filter failed");
      await page.selectOption("#source-filter", "search-engine-land-meta-rss");
      assert(await page.locator("#update-list .update-card").count() === 2, "personal feed source filter failed");
      await page.fill("#query-filter", "表示変更");
      assert(await page.locator("#update-list .update-card").count() === 1, "personal feed query filter failed");
      await page.click("#reset-button");
      assert(await page.locator("#update-list .update-card").count() === 3, "personal feed reset failed");
    }
    if (artifactDirectory) {
      await page.screenshot({ path: path.join(artifactDirectory, `personal-feed-${viewport.name}-viewport.png`) });
      await page.screenshot({ path: path.join(artifactDirectory, `personal-feed-${viewport.name}-full-page.png`), fullPage: true });
    }
    await page.close();
  }

  for (const viewport of [viewports[0], viewports[2]]) {
    const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
    const label = `delayed-recovery/${viewport.name}`;
    await page.goto(`${server.origin}/meta-ads-updates/index.html?fixture=delayed-recovery`, { waitUntil: "networkidle" });
    assert(await page.locator("#recovery-banner").isVisible(), `${label}: delayed-recovery banner is missing`);
    assert((await page.locator("#recovery-banner").textContent()).includes("金曜17:00 MYTの締切前candidateが不足"), `${label}: delayed-recovery banner is misleading`);
    assert(!(await page.locator("#demo-banner").isVisible()), `${label}: delayed recovery must not be labelled as a demo`);
    assert(await page.locator("#update-list .update-card").count() === 3, `${label}: recovery cards are missing`);
    await assertTokens(page);
    await assertAccessibilityAndLayout(page, label);
    if (artifactDirectory) {
      await page.screenshot({ path: path.join(artifactDirectory, `delayed-recovery-${viewport.name}-viewport.png`) });
      await page.screenshot({ path: path.join(artifactDirectory, `delayed-recovery-${viewport.name}-full-page.png`), fullPage: true });
    }
    await page.close();
  }

  for (const viewport of [viewports[0], viewports[2]]) {
    const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    const label = `demo/${viewport.name}`;
    await page.goto(`${server.origin}/meta-ads-updates/index.html?demo=1`, { waitUntil: "networkidle" });
    assert(await page.locator("#demo-banner").isVisible(), `${label}: demo banner is missing`);
    assert(await page.locator("#demo-banner").evaluate((node) => node.textContent.replace(/\s+/g, " ").trim()) === "デモ環境 架空データを表示しています。実運用の承認・判断には使用しないでください。", `${label}: demo banner text changed`);
    assert(await page.locator("#update-list .update-card").count() === demoReport.items.length, `${label}: unexpected demo card count`);
    assert((await page.locator("#result-summary").textContent()).includes("デモ用の架空更新"), `${label}: demo summary is misleading`);
    assert(await page.locator(".source-link").evaluateAll((links) => links.every((link) =>
      link.textContent === "公式ソース例を開く" &&
      link.href.startsWith("https://") &&
      link.target === "_blank" &&
      link.rel.includes("noreferrer") &&
      !link.href.includes("example.test")
    )), `${label}: demo source links are unsafe or misleading`);
    assert(consoleErrors.length === 0 && pageErrors.length === 0, `${label}: runtime errors: ${[...consoleErrors, ...pageErrors].join("; ")}`);
    await assertTokens(page);
    await assertAccessibilityAndLayout(page, label);
    if (artifactDirectory) {
      await page.screenshot({ path: path.join(artifactDirectory, `demo-${viewport.name}-viewport.png`) });
      await page.screenshot({ path: path.join(artifactDirectory, `demo-${viewport.name}-full-page.png`), fullPage: true });
    }
    if (viewport.name === "desktop") {
      await page.selectOption("#source-filter", "meta-product-news-rss");
      assert(await page.locator("#update-list .update-card").count() === 3, "demo Product News filter failed");
      await page.click("#reset-button");
      await page.selectOption("#source-filter", "meta-business-sdk-releases");
      assert(await page.locator("#update-list .update-card").count() === 1, "demo SDK filter failed");
      await page.click("#reset-button");
      await page.selectOption("#priority-filter", "high");
      assert(await page.locator("#update-list .update-card").count() === 1, "demo high-priority filter failed");
      await page.click("#reset-button");
      await page.fill("#query-filter", "設定手順B");
      assert(await page.locator("#update-list .update-card").count() === 1, "demo query filter failed");
      await page.selectOption("#priority-filter", "high");
      assert(await page.locator("#update-list .update-card").count() === 0, "demo combined filters must show no results");
      assert(await page.locator("#empty-state").isVisible(), "demo filtered empty state is missing");
      await page.click("#reset-button");
      assert(await page.locator("#update-list .update-card").count() === demoReport.items.length, "demo reset failed");
    }
    await page.close();
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
  await page.close();
  console.log(`PASS: production UI ${caseCount}/15 fixture viewport cases plus production and demo E2E flows, overflow, targets, focus, axe, and approved tokens`);
} finally {
  await browser.close();
  await server.close();
}
