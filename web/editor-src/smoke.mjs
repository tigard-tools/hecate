import { startServer, launchBrowser } from "./harness.mjs";

const { server, port } = await startServer();
const { browser, page, errors } = await launchBrowser();
await page.goto(`http://localhost:${port}/editor-src/smoke.html`, { waitUntil: "networkidle0" });
await page.waitForSelector(".cm-editor", { timeout: 5000 });
const res = await page.evaluate(() => window.__smoke);
console.log("smoke:", JSON.stringify(res));
console.log("console errors:", errors.length ? errors : "none");
await browser.close();
server.close();
const ok = res && res.hasEditor && res.tokenSpans > 0 && res.docMatches && errors.length === 0;
console.log(ok ? "PASS" : "FAIL");
process.exit(ok ? 0 : 1);
