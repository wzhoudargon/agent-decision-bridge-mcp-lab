const { chromium } = require("playwright");
const path = require("path");

async function main() {
  const root = __dirname;
  const browser = await chromium.launch({
    headless: true,
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1600 }, deviceScaleFactor: 1 });
  await page.goto(`file://${path.join(root, "index.html")}`, { waitUntil: "networkidle" });
  await page.evaluate(async () => {
    if (document.fonts) await document.fonts.ready;
    if (window.lucide && typeof window.lucide.createIcons === "function") window.lucide.createIcons();
  });
  const targets = [
    ["#xhs-01", "xhs-01-cover.png"],
    ["#xhs-02", "xhs-02-before-after.png"],
    ["#xhs-03", "xhs-03-permissions.png"],
    ["#xhs-04", "xhs-04-workflow.png"],
    ["#xhs-05", "xhs-05-safety.png"],
    ["#xhs-06", "xhs-06-github.png"],
  ];
  for (const [selector, filename] of targets) {
    const poster = page.locator(selector);
    await poster.screenshot({ path: path.join(root, "output", filename) });
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
