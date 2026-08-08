// Loads the REAL index.html in headless Chromium and asserts the app boots,
// CodeMirror mounts, and nothing throws. File System Access / Web Serial are
// absent headless (the app shows its landing screen) but initEditor() still runs.
import { startServer, launchBrowser } from "./harness.mjs";

const { server, port } = await startServer();
const { browser, page, errors } = await launchBrowser();
await page.goto(`http://localhost:${port}/index.html`, { waitUntil: "networkidle0" });
await page.waitForSelector(".cm-editor", { timeout: 5000 });

const result = await page.evaluate(() => ({
  hasEditor: !!document.querySelector(".cm-editor"),
  // initEditor mounts read-only until a file loads; no drive headless => stays RO
  readOnlyInitially: document.querySelector(".cm-content")?.getAttribute("contenteditable") === "false",
  hasPlaceholder: !!document.querySelector(".cm-placeholder"),
  // landing is shown (nothing connected), console hidden — app booted its normal path
  landingShown: !document.getElementById("landing").hidden,
}));
console.log("app-smoke:", JSON.stringify(result));
console.log("console errors:", errors.length ? errors : "none");
await browser.close();
server.close();
const ok = result.hasEditor && result.readOnlyInitially && errors.length === 0;
console.log(ok ? "PASS" : "FAIL");
process.exit(ok ? 0 : 1);
