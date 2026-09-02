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
const personalFeedV3Report = JSON.parse(await fs.readFile(path.join(repositoryRoot, "scripts/fixtures/meta_ads_personal_feed_v3.json"), "utf8"));
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
    schemaVersion: "meta-ads-personal-feed/v2",
    generatedAt: "2026-08-29T09:00:00Z",
    sources,
    items: [
      { id: "meta-product-news-rss-aaaaaaaaaaaaaaaaaaaa", sourceId: "meta-product-news-rss", title: "Meta公式の製品更新", url: "https://about.fb.com/news/2026/08/product-update/", publishedDate: "2026-08-29", updatedDate: null, firstObservedAt: "2026-08-29T09:00:00Z", lastObservedAt: "2026-08-29T09:00:00Z", platforms: ["Metaプラットフォーム全般"], matchEvidence: [], presentation: { schemaVersion: "meta-ads-personal-feed-presentation/v1", status: "generated", shortHeadlineJa: "Meta公式の製品更新", summaryJa: "Metaの製品更新に関するお知らせです。", sourceFingerprint: "a".repeat(64), generatedAt: "2026-08-29T09:00:00Z" } },
      { id: "search-engine-land-meta-rss-bbbbbbbbbbbbbbbbbbbb", sourceId: "search-engine-land-meta-rss", title: "Meta Ads APIの観測記事", url: "https://searchengineland.com/meta-ads-api/", publishedDate: "2026-08-28", updatedDate: "2026-08-29", firstObservedAt: "2026-08-29T09:00:00Z", lastObservedAt: "2026-08-29T09:00:00Z", platforms: ["Meta Ads"], matchEvidence: ["category:PPC"], presentation: { schemaVersion: "meta-ads-personal-feed-presentation/v1", status: "generated", shortHeadlineJa: "Meta Ads APIの観測", summaryJa: "Meta Ads APIに関する観測記事です。", sourceFingerprint: "b".repeat(64), generatedAt: "2026-08-29T09:00:00Z" } },
      { id: "search-engine-land-meta-rss-cccccccccccccccccccc", sourceId: "search-engine-land-meta-rss", title: "Meta Adsの表示変更", url: "https://searchengineland.com/meta-ads-ui/", publishedDate: null, updatedDate: null, firstObservedAt: "2026-08-29T09:00:00Z", lastObservedAt: "2026-08-29T09:00:00Z", platforms: ["Meta Ads"], matchEvidence: ["category:PPC"], presentation: { schemaVersion: "meta-ads-personal-feed-presentation/v1", status: "pending", shortHeadlineJa: null, summaryJa: null, sourceFingerprint: "c".repeat(64), generatedAt: null } }
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
        if (referer.searchParams.get("personal-fixture") === "v3") {
          response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
          return response.end(JSON.stringify(personalFeedV3Report));
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
  const undersized = await page.locator("button, select, input, .source-link, .detail-link, .back-link, .locale-switch a").evaluateAll((nodes) =>
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
  assert(["locale-en", "source-filter"].includes(focus.id) && focus.outline !== "none" && focus.width === "3px", `${label}: keyboard focus is not visibly styled`);
  await page.addScriptTag({ content: axeSource });
  const axe = await page.evaluate(async () => globalThis.axe.run(document, { runOnly: ["wcag2a", "wcag2aa"] }));
  assert(axe.violations.length === 0, `${label}: axe violations: ${axe.violations.map((item) => item.id).join(", ")}`);
}

async function assertDetailAccessibilityAndLayout(page, label) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert(overflow <= 1, `${label}: horizontal overflow ${overflow}px`);
  const undersized = await page.locator(".source-link, .back-link, .locale-switch a").evaluateAll((nodes) =>
    nodes.map((node) => ({ text: node.textContent, rect: node.getBoundingClientRect() }))
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
  assert(focus.id === "back-link" && focus.outline !== "none" && focus.width === "3px", `${label}: keyboard focus is not visibly styled`);
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
  const productionConsoleErrors = [];
  const productionPageErrors = [];
  productionPage.on("console", (message) => { if (message.type() === "error") productionConsoleErrors.push(message.text()); });
  productionPage.on("pageerror", (error) => productionPageErrors.push(error.message));
  await productionPage.goto(`${server.origin}/meta-ads-updates/index.html`, { waitUntil: "networkidle" });
  assert(await productionPage.locator("#update-list .update-card").count() === personalFeedReport.items.length, `production route did not read personal-feed.json: ${[...productionConsoleErrors, ...productionPageErrors].join("; ")}`);
  assert(!(await productionPage.locator("#demo-banner").isVisible()), "production route must not show the demo banner");
  assert(!(await productionPage.locator("#recovery-banner").isVisible()), "ordinary production route must not show the delayed-recovery banner");
  assert(await productionPage.locator("#unofficial-notice").isVisible(), "Personal Feed must show the non-official-source notice");
  const unofficialNotice = await productionPage.locator("#unofficial-notice").textContent();
  assert(unofficialNotice.includes("do not represent Meta’s official position") && unofficialNotice.includes("cross-check with additional sources"), "English Personal Feed notice must explain how unofficial information is handled");
  assert(!unofficialNotice.includes("must be confirmed by Meta"), "Personal Feed must not imply that every unofficial item has an official counterpart");
  await productionPage.close();

  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    const label = `personal-feed/${viewport.name}`;
    await page.goto(`${server.origin}/meta-ads-updates/ja/?personal-fixture=1`, { waitUntil: "networkidle" });
    assert(await page.locator("#unofficial-notice").isVisible(), `${label}: non-official notice is missing`);
    assert(await page.locator("#update-list .update-card").count() === 3, `${label}: personal feed cards are missing`);
    assert(await page.locator(".origin-label--official").count() === 1, `${label}: official badge is missing`);
    assert(await page.locator(".origin-label--unofficial").count() === 2, `${label}: non-official badge is missing`);
    assert(await page.locator(".detail-link").count() === 3, `${label}: detail links are missing`);
    assert(await page.locator(".source-link").count() === 0, `${label}: Personal Feed list must not expose article links directly`);
    assert((await page.locator("#update-list h2").allTextContents()).includes("Meta Ads APIの観測"), `${label}: generated Japanese headline is missing from the list`);
    assert(await page.locator(".unofficial-copy").count() === 0, `${label}: per-card non-official warning must not be rendered`);
    assert((await page.locator(".fact-label").allTextContents()).filter((label) => label === "最終更新日").length === 3, `${label}: final update date label is missing`);
    assert(!(await page.locator(".fact-label").allTextContents()).includes("対象"), `${label}: target platform must not be shown on the Personal Feed list`);
    assert(await page.locator(".fact-grid > div").evaluateAll((nodes) => nodes
      .filter((node) => node.querySelector(".fact-label")?.textContent === "最終更新日")
      .filter((node) => node.querySelector("dd")?.textContent === "確認できず")
      .every((node) => getComputedStyle(node.querySelector("dd")).fontStyle === "normal")), `${label}: unknown final update date must use normal typography`);
    assert(!(await page.locator(".fact-label").allTextContents()).includes("最終確認"), `${label}: automated observation timestamp must not be shown as human confirmation`);
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

  const v3List = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const v3ListConsoleErrors = [];
  const v3ListPageErrors = [];
  v3List.on("console", (message) => { if (message.type() === "error") v3ListConsoleErrors.push(message.text()); });
  v3List.on("pageerror", (error) => v3ListPageErrors.push(error.message));
  await v3List.goto(`${server.origin}/meta-ads-updates/ja/?personal-fixture=v3`, { waitUntil: "networkidle" });
  assert(await v3List.locator("#update-list .update-card").count() === personalFeedV3Report.items.length, "v3 Personal Feed list did not render");
  assert((await v3List.locator("#update-list h2").allTextContents()).includes("Meta広告の計測機能を更新"), "v3 list did not use its Japanese locale overlay");
  assert(await v3List.locator(".detail-link").first().getAttribute("href").then((href) => href?.includes("personal-fixture=v3")), "v3 detail links did not retain the fixed fixture selector");
  assert(await v3List.locator("#update-list").textContent().then((text) => !text.includes("machine") && !text.includes("missing")), "v3 list must not expose presentation status");
  assert(v3ListConsoleErrors.length === 0 && v3ListPageErrors.length === 0, `v3 Personal Feed list runtime errors: ${[...v3ListConsoleErrors, ...v3ListPageErrors].join("; ")}`);
  await assertTokens(v3List);
  await assertAccessibilityAndLayout(v3List, "personal-feed-v3/desktop");
  await v3List.close();

  for (const viewport of [viewports[0], viewports[2]]) {
    const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
    const consoleErrors = [];
    const pageErrors = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    const label = `personal-detail/${viewport.name}`;
    await page.goto(`${server.origin}/meta-ads-updates/ja/?personal-fixture=1`, { waitUntil: "networkidle" });
    await page.selectOption("#source-filter", "search-engine-land-meta-rss");
    await page.selectOption("#priority-filter", "unofficial");
    await page.fill("#query-filter", "表示変更");
    const href = await page.locator(".detail-link").getAttribute("href");
    assert(href?.includes("personal-fixture=1") && href.includes("source=search-engine-land-meta-rss") && href.includes("type=unofficial") && href.includes("q=%E8%A1%A8%E7%A4%BA%E5%A4%89%E6%9B%B4"), `${label}: detail link did not preserve filters`);
    await page.locator(".detail-link").click();
    await page.waitForURL(/detail\.html\?/);
    assert(await page.locator("#detail-card").isVisible(), `${label}: detail card is missing`);
    assert((await page.locator("#detail-title").textContent()).includes("Meta Adsの表示変更"), `${label}: Japanese short headline is missing`);
    assert((await page.locator("#detail-summary").textContent()).includes("要約は利用できません"), `${label}: pending-summary fallback is missing`);
    assert((await page.locator("#detail-original-title").textContent()).includes("Meta Adsの表示変更"), `${label}: original title is missing`);
    assert(!(await page.locator(".fact-label").allTextContents()).includes("最終確認"), `${label}: automated observation timestamp must not be shown on detail page`);
    assert(await page.locator("#detail-unofficial-notice").isVisible(), `${label}: non-official notice is missing`);
    const detailNotice = await page.locator("#detail-unofficial-notice").textContent();
    assert(detailNotice.includes("公式情報で確認できない内容もあるため") && detailNotice.includes("複数の情報源や実環境で追加確認"), `${label}: detail notice must explain that official confirmation may not exist`);
    assert(await page.locator("#detail-source-link").evaluate((link) => link.href.startsWith("https://") && link.target === "_blank" && link.rel.includes("noreferrer")), `${label}: source link is unsafe`);
    assert((await page.locator("#back-link").getAttribute("href")).includes("source=search-engine-land-meta-rss"), `${label}: back link did not preserve filters`);
    assert(consoleErrors.length === 0 && pageErrors.length === 0, `${label}: runtime errors: ${[...consoleErrors, ...pageErrors].join("; ")}`);
    await assertDetailAccessibilityAndLayout(page, label);
    if (artifactDirectory) {
      await page.screenshot({ path: path.join(artifactDirectory, `personal-detail-${viewport.name}-viewport.png`) });
      await page.screenshot({ path: path.join(artifactDirectory, `personal-detail-${viewport.name}-full-page.png`), fullPage: true });
    }
    await page.locator("#back-link").click();
    await page.waitForURL(/\/ja\/\?/);
    assert(await page.locator("#source-filter").inputValue() === "search-engine-land-meta-rss", `${label}: source filter was not restored`);
    assert(await page.locator("#priority-filter").inputValue() === "unofficial", `${label}: classification filter was not restored`);
    assert(await page.locator("#query-filter").inputValue() === "表示変更", `${label}: query filter was not restored`);
    await page.close();
  }

  const missingDetail = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await missingDetail.goto(`${server.origin}/meta-ads-updates/ja/detail.html?id=missing-item&personal-fixture=1`, { waitUntil: "networkidle" });
  assert(await missingDetail.locator("#detail-error").isVisible(), "missing detail must show a safe error state");
  assert(!(await missingDetail.locator("#detail-card").isVisible()), "missing detail must not show a card");
  await missingDetail.close();

  const generatedDetail = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await generatedDetail.goto(`${server.origin}/meta-ads-updates/ja/detail.html?id=search-engine-land-meta-rss-bbbbbbbbbbbbbbbbbbbb&personal-fixture=1`, { waitUntil: "networkidle" });
  assert((await generatedDetail.locator("#detail-title").textContent()) === "Meta Ads APIの観測", "generated detail must use the Japanese short headline");
  assert((await generatedDetail.locator("#detail-summary").textContent()).includes("Meta Ads APIに関する観測記事です。"), "generated detail must display the Japanese summary");
  assert(await generatedDetail.locator("#detail-unofficial-notice").isVisible(), "generated non-official detail must show the notice");
  await generatedDetail.close();

  const v3MachineDetail = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await v3MachineDetail.goto(`${server.origin}/meta-ads-updates/ja/detail.html?id=meta-product-news-rss-aaaaaaaaaaaaaaaaaaaa&personal-fixture=v3`, { waitUntil: "networkidle" });
  assert((await v3MachineDetail.locator("#detail-title").textContent()) === "Meta広告の計測機能を更新", "v3 detail must use the Japanese locale headline");
  assert((await v3MachineDetail.locator("#detail-summary").textContent()).includes("広告主向け計測機能の更新"), "v3 detail must use the Japanese locale summary");
  assert((await v3MachineDetail.locator("#detail-facts").textContent()).includes("Metaプラットフォーム全般"), "v3 detail must translate platform IDs for the current Japanese UI");
  assert(!(await v3MachineDetail.locator("#detail-unofficial-notice").isVisible()), "v3 official detail must not show an unofficial notice");
  await v3MachineDetail.close();

  const v3MissingDetail = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await v3MissingDetail.goto(`${server.origin}/meta-ads-updates/ja/detail.html?id=social-media-today-meta-ads-bbbbbbbbbbbbbbbbbbbb&personal-fixture=v3`, { waitUntil: "networkidle" });
  assert((await v3MissingDetail.locator("#detail-title").textContent()) === "Meta Ads source article", "v3 missing detail must fall back to the original title");
  assert((await v3MissingDetail.locator("#detail-summary").textContent()).includes("要約は利用できません"), "v3 missing detail must show the Japanese fallback");
  assert(await v3MissingDetail.locator("#detail-unofficial-notice").isVisible(), "v3 unofficial detail must show the notice");
  await v3MissingDetail.close();

  const productionDetail = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const legacyItem = personalFeedReport.items[0];
  await productionDetail.goto(`${server.origin}/meta-ads-updates/detail.html?id=${encodeURIComponent(legacyItem.id)}`, { waitUntil: "networkidle" });
  assert(await productionDetail.locator("#detail-card").isVisible(), "v1 production feed detail must render");
  assert((await productionDetail.locator("#detail-title").textContent()) === legacyItem.title, "English root must fall back to the original title for a v2 Japanese-only presentation");
  assert((await productionDetail.locator("#detail-summary").textContent()) === "Summary not available. Review the original source.", "English root must not translate a Japanese-only v2 presentation back into English");
  await productionDetail.close();

  for (const viewport of [viewports[0], viewports[2]]) {
    const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
    const label = `delayed-recovery/${viewport.name}`;
    await page.goto(`${server.origin}/meta-ads-updates/index.html?fixture=delayed-recovery`, { waitUntil: "networkidle" });
    assert(await page.locator("#recovery-banner").isVisible(), `${label}: delayed-recovery banner is missing`);
    assert((await page.locator("#recovery-banner").textContent()).includes("Friday 17:00 MYT cutoff"), `${label}: delayed-recovery banner is misleading`);
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
  const englishList = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await englishList.goto(`${server.origin}/meta-ads-updates/?personal-fixture=v3&source=meta-product-news-rss&type=official&q=measurement`, { waitUntil: "networkidle" });
  assert(await englishList.locator("html").getAttribute("lang") === "en", "root route must be English");
  assert((await englishList.locator("#update-list h2").textContent()) === "Meta Ads measurement update", "English route must use the English overlay");
  assert(await englishList.locator("#update-list").textContent().then((text) => !text.includes("machine") && !text.includes("missing")), "list cards must not expose generation status");
  assert(await englishList.locator("#locale-ja").getAttribute("href").then((href) => href === "/meta-ads-updates/ja/?source=meta-product-news-rss&type=official&q=measurement&personal-fixture=v3"), "language switch must retain supported list filters");
  assert(await englishList.locator("#canonical-link").getAttribute("href") === "https://ysmsnsmr.github.io/meta-ads-updates/", "English list canonical is incorrect");
  assert(await englishList.locator("#alternate-ja").getAttribute("href") === "https://ysmsnsmr.github.io/meta-ads-updates/ja/", "English list hreflang is incorrect");
  await assertAccessibilityAndLayout(englishList, "english-list/desktop");
  await englishList.locator(".detail-link").click();
  await englishList.waitForURL(/detail\.html\?/);
  assert((await englishList.locator("#detail-title").textContent()) === "Meta Ads measurement update", "English detail must use the English overlay");
  assert((await englishList.locator("#detail-presentation-status").textContent()) === "Machine-generated summary", "detail must disclose a machine-generated summary");
  assert(await englishList.locator('meta[name="robots"]').getAttribute("content") === "noindex,follow", "detail must be noindex,follow");
  assert(await englishList.locator("#canonical-link").getAttribute("href").then((href) => href?.startsWith("https://ysmsnsmr.github.io/meta-ads-updates/detail.html?id=")), "English detail canonical is incorrect");
  assert(await englishList.locator("#alternate-ja").getAttribute("href").then((href) => href?.startsWith("https://ysmsnsmr.github.io/meta-ads-updates/ja/detail.html?id=")), "English detail hreflang is incorrect");
  assert(await englishList.locator("#locale-ja").getAttribute("href").then((href) => href?.includes("/ja/detail.html?id=") && href.includes("source=meta-product-news-rss") && href.includes("type=official") && href.includes("q=measurement")), "detail language switch must retain id and filters");
  await englishList.close();

  const englishMissing = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await englishMissing.goto(`${server.origin}/meta-ads-updates/detail.html?id=social-media-today-meta-ads-bbbbbbbbbbbbbbbbbbbb&personal-fixture=v3`, { waitUntil: "networkidle" });
  assert((await englishMissing.locator("#detail-summary").textContent()) === "Summary not available. Review the original source.", "English detail must describe a missing summary without invention");
  assert((await englishMissing.locator("#detail-presentation-status").textContent()) === "Summary not available", "missing summary status is absent");
  await englishMissing.close();

  const japaneseDemoRedirect = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await japaneseDemoRedirect.goto(`${server.origin}/meta-ads-updates/?demo=1`, { waitUntil: "networkidle" });
  assert(new URL(japaneseDemoRedirect.url()).pathname === "/meta-ads-updates/ja/", "root demo URL must redirect to the Japanese demo route");
  assert(await japaneseDemoRedirect.locator("#locale-en").getAttribute("href") === "/meta-ads-updates/", "Japanese demo must not carry its demo query into a normal language route");
  await japaneseDemoRedirect.close();
  console.log(`PASS: production UI ${caseCount}/15 fixture viewport cases plus English/Japanese routes, detail status, SEO metadata, demo redirect, and existing E2E flows`);
} finally {
  await browser.close();
  await server.close();
}
