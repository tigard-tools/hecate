import puppeteer from "puppeteer-core";
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname; // the web/ dir
const MIME = { ".html": "text/html", ".js": "text/javascript",
               ".css": "text/css", ".ico": "image/x-icon" };

export async function startServer() {
  const server = http.createServer(async (req, res) => {
    if (req.url === "/favicon.ico") { res.writeHead(204); res.end(); return; }
    try {
      const rel = normalize(decodeURIComponent(req.url.split("?")[0])).replace(/^(\.\.[/\\])+/, "");
      const body = await readFile(join(ROOT, rel === "/" ? "index.html" : rel));
      res.writeHead(200, { "content-type": MIME[extname(rel)] || "application/octet-stream" });
      res.end(body);
    } catch {
      res.writeHead(404); res.end("nope");
    }
  });
  await new Promise((r) => server.listen(0, r));
  return { server, port: server.address().port };
}

export async function launchBrowser() {
  const browser = await puppeteer.launch({
    executablePath: process.env.CHROMIUM || "/usr/bin/chromium",
    headless: "new",
    args: ["--no-sandbox"],
  });
  const page = await browser.newPage();
  const errors = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !/favicon/.test(m.text())) errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(String(e)));
  return { browser, page, errors };
}
