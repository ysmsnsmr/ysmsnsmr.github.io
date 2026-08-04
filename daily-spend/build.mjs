import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectDirectory = path.dirname(fileURLToPath(import.meta.url));
const outputDirectory = path.join(projectDirectory, "dist", "server");
const assetDefinitions = [
  ["/index.html", "index.html", "text/html; charset=utf-8"],
  ["/styles.css", "styles.css", "text/css; charset=utf-8"],
  ["/storage.js", "storage.js", "text/javascript; charset=utf-8"],
  ["/app.js", "app.js", "text/javascript; charset=utf-8"],
  [
    "/service-worker.js",
    "service-worker.js",
    "text/javascript; charset=utf-8"
  ],
  [
    "/manifest.webmanifest",
    "manifest.webmanifest",
    "application/manifest+json; charset=utf-8"
  ],
  ["/icons/icon-192.png", "icons/icon-192.png", "image/png"],
  ["/icons/icon-512.png", "icons/icon-512.png", "image/png"],
  [
    "/icons/apple-touch-icon.png",
    "icons/apple-touch-icon.png",
    "image/png"
  ]
];

const assets = assetDefinitions.map(([urlPath, sourcePath, contentType]) => {
  const bytes = fs.readFileSync(path.join(projectDirectory, sourcePath));
  return [
    urlPath,
    {
      body: bytes.toString("base64"),
      contentType,
      immutable: urlPath.startsWith("/icons/")
    }
  ];
});

const workerSource = `const ASSETS = new Map(${JSON.stringify(assets)});
const SECURITY_HEADERS = {
  "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY"
};

function decodeBase64(value) {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export default {
  async fetch(request) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD", ...SECURITY_HEADERS }
      });
    }

    const url = new URL(request.url);
    const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
    const asset = ASSETS.get(pathname);
    if (!asset) {
      return new Response("Not found", {
        status: 404,
        headers: SECURITY_HEADERS
      });
    }

    const headers = new Headers({
      "Content-Type": asset.contentType,
      "Cache-Control": asset.immutable
        ? "public, max-age=31536000, immutable"
        : "no-cache",
      ...SECURITY_HEADERS
    });
    if (pathname === "/service-worker.js") {
      headers.set("Service-Worker-Allowed", "/");
    }
    return new Response(
      request.method === "HEAD" ? null : decodeBase64(asset.body),
      { status: 200, headers }
    );
  }
};
`;

fs.rmSync(path.join(projectDirectory, "dist"), {
  recursive: true,
  force: true
});
fs.mkdirSync(outputDirectory, { recursive: true });
fs.writeFileSync(
  path.join(outputDirectory, "index.js"),
  workerSource,
  "utf8"
);
