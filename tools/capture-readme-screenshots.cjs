const fs = require("node:fs/promises");
const path = require("node:path");
const { spawn } = require("node:child_process");

const root = process.cwd();
const screenshotsDir = path.join(root, "docs", "screenshots");
const profileDir = path.join(root, `.tmp-readme-chrome-profile-${Date.now()}`);
const chromePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const port = 9230 + Math.floor(Math.random() * 500);
const targetUrl = "http://localhost:15173";

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitForJson(pathname, chrome) {
  for (let i = 0; i < 50; i += 1) {
    if (chrome?.exitCode !== null) {
      throw new Error(`Chrome terminato prima di esporre DevTools: ${chrome.exitCode}`);
    }
    try {
      const response = await fetch(`http://127.0.0.1:${port}${pathname}`);
      if (response.ok) return await response.json();
    } catch {
      // Chrome is still starting.
    }
    await sleep(200);
  }
  throw new Error(`Chrome DevTools non disponibile: ${pathname}`);
}

async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });

  let id = 0;
  const pending = new Map();

  ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result);
  });

  return {
    send(method, params = {}) {
      const messageId = ++id;
      ws.send(JSON.stringify({ id: messageId, method, params }));
      return new Promise((resolve, reject) => pending.set(messageId, { resolve, reject }));
    },
    close() {
      ws.close();
    },
  };
}

async function waitForExpression(client, expression, timeoutMs = 15000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const result = await client.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (result.result?.value) return;
    await sleep(300);
  }
  throw new Error(`Timeout waiting for: ${expression}`);
}

async function clickByText(client, text) {
  const result = await client.send("Runtime.evaluate", {
    expression: `(() => {
      const wanted = ${JSON.stringify(text)};
      const button = Array.from(document.querySelectorAll("button"))
        .find((item) => (item.textContent || "").trim().includes(wanted));
      if (!button) return false;
      button.click();
      return true;
    })()`,
    returnByValue: true,
  });
  if (!result.result?.value) throw new Error(`Pulsante non trovato: ${text}`);
}

async function clickMode(client, text) {
  const result = await client.send("Runtime.evaluate", {
    expression: `(() => {
      const wanted = ${JSON.stringify(text)};
      const button = Array.from(document.querySelectorAll(".mode-tabs button"))
        .find((item) => (item.textContent || "").trim() === wanted);
      if (!button) return false;
      button.click();
      return true;
    })()`,
    returnByValue: true,
  });
  if (!result.result?.value) throw new Error(`Tab non trovata: ${text}`);
}

async function capture(client, fileName) {
  await sleep(900);
  const screenshot = await client.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
  });
  await fs.writeFile(path.join(screenshotsDir, fileName), Buffer.from(screenshot.data, "base64"));
  console.log(`saved ${fileName}`);
}

async function main() {
  console.log("prepare");
  await fs.mkdir(screenshotsDir, { recursive: true });
  await fs.mkdir(profileDir, { recursive: true });

  console.log("launch chrome");
  const chrome = spawn(
    chromePath,
    [
      "--headless=new",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${profileDir}`,
      "--window-size=1440,1000",
      "--force-device-scale-factor=1",
      "--disable-gpu",
      "--disable-extensions",
      "--no-sandbox",
      "--no-first-run",
      "--no-default-browser-check",
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  try {
    console.log("wait devtools");
    await waitForJson("/json/version", chrome);
    console.log("list tabs");
    const tabs = await waitForJson("/json/list", chrome);
    const page = tabs.find((item) => item.type === "page") || tabs[0];
    if (!page?.webSocketDebuggerUrl) throw new Error("Nessun tab CDP disponibile");

    console.log("connect");
    const client = await connect(page.webSocketDebuggerUrl);
    console.log("enable");
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: 1440,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await client.send("Page.navigate", { url: targetUrl });
    console.log("wait app");
    await waitForExpression(client, `document.body && document.body.innerText.includes("PostgreSQL Sandbox")`);
    await waitForExpression(client, `document.body.innerText.includes("SQL diretto")`);
    await sleep(2500);

    await clickByText(client, "Esegui");
    await waitForExpression(client, `document.body.innerText.includes("Risultati SQL")`);
    await waitForExpression(client, `!document.body.innerText.includes("Loading...")`, 25000);
    await sleep(1000);
    await capture(client, "sql-workbench.png");

    await clickMode(client, "Dashboard");
    await waitForExpression(client, `document.body.innerText.includes("Aggiungi scheda")`);
    await sleep(2500);
    await capture(client, "dashboard.png");

    await clickMode(client, "Tabelle complete");
    await waitForExpression(client, `document.body.innerText.includes("Tabelle complete")`);
    await sleep(2000);
    await capture(client, "table-browser.png");

    client.close();
  } finally {
    chrome.kill("SIGTERM");
    await sleep(500);
    await fs.rm(profileDir, { recursive: true, force: true });
  }
}

const keepAlive = setInterval(() => {}, 1000);

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(() => {
    clearInterval(keepAlive);
  });
