import assert from "node:assert/strict";
import test from "node:test";
import worker from "../dist/server/index.js";

test("serves the app from the Site origin root", async () => {
  const response = await worker.fetch(
    new Request("https://one-next-task.example/")
  );
  const html = await response.text();

  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type"), /^text\/html/);
  assert.match(html, /<title>ひとつだけ<\/title>/);
  assert.match(html, /\.\/manifest\.webmanifest/);
  assert.match(
    response.headers.get("content-security-policy"),
    /default-src 'self'/
  );
});

test("serves PWA assets with the required headers", async () => {
  const manifest = await worker.fetch(
    new Request("https://one-next-task.example/manifest.webmanifest")
  );
  const serviceWorker = await worker.fetch(
    new Request("https://one-next-task.example/service-worker.js")
  );
  const icon = await worker.fetch(
    new Request("https://one-next-task.example/icons/icon-192.png")
  );

  assert.equal(manifest.status, 200);
  assert.match(
    manifest.headers.get("content-type"),
    /^application\/manifest\+json/
  );
  assert.equal(serviceWorker.headers.get("service-worker-allowed"), "/");
  assert.match(icon.headers.get("cache-control"), /immutable/);
  assert.ok((await icon.arrayBuffer()).byteLength > 1000);
});

test("does not leak missing assets or accept writes", async () => {
  const missing = await worker.fetch(
    new Request("https://one-next-task.example/private")
  );
  const post = await worker.fetch(
    new Request("https://one-next-task.example/", { method: "POST" })
  );

  assert.equal(missing.status, 404);
  assert.equal(await missing.text(), "Not found");
  assert.equal(post.status, 405);
  assert.equal(post.headers.get("allow"), "GET, HEAD");
});
