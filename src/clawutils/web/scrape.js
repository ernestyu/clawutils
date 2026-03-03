// clawutils web scraper
//
// This script is the current reference implementation for "clawutils web scrape".
// It uses Playwright + Readability + Turndown to extract main article content
// and emit normalized markdown in the following format:
//
//   --- METADATA ---
//   Title: ...
//   Author: ...
//   Site: ...
//   FinalURL: ...
//   Extraction: readability|fallback-container|body-innerText|github-raw-fast-path
//   FallbackSelector: ...   # only when not readability
//   --- MARKDOWN ---
//   <markdown>
//
// The logic is adapted from your existing Node.js helper script, with only
// cosmetic changes (comments, formatting) so that it can live inside the
// clawutils repo and be invoked via the unified CLI.

const { chromium } = require("playwright");
const { Readability } = require("@mozilla/readability");
const { JSDOM } = require("jsdom");
const TurndownService = require("turndown");

const url = process.argv[2];

if (!url || !/^https?:\/\//i.test(url)) {
  console.error("ERROR: Please provide a valid http/https URL as argv[2].");
  process.exit(2);
}

function nowIso() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

async function waitForStableText(
  page,
  { minLen = 800, stableRounds = 3, intervalMs = 700, timeoutMs = 30000 } = {}
) {
  const start = Date.now();
  let lastLen = 0;
  let stable = 0;

  while (Date.now() - start < timeoutMs) {
    const len = await page.evaluate(
      () =>
        document.body && document.body.innerText
          ? document.body.innerText.length
          : 0
    );

    if (len >= minLen && Math.abs(len - lastLen) < 30) {
      stable += 1;
      if (stable >= stableRounds) return len;
    } else {
      stable = 0;
    }

    lastLen = len;
    await page.waitForTimeout(intervalMs);
  }

  return await page.evaluate(
    () =>
      document.body && document.body.innerText
        ? document.body.innerText.length
        : 0
  );
}

async function smartAutoScroll(
  page,
  { maxSteps = 40, stepPx = 700, delayMs = 80, maxMs = 12000 } = {}
) {
  const start = Date.now();
  let lastHeight = await page.evaluate(() => document.body.scrollHeight);
  let stagnantRounds = 0;

  for (let i = 0; i < maxSteps; i++) {
    if (Date.now() - start > maxMs) break;

    await page.evaluate((y) => window.scrollBy(0, y), stepPx);
    await page.waitForTimeout(delayMs);

    const h = await page.evaluate(() => document.body.scrollHeight);
    if (h <= lastHeight + 10) {
      stagnantRounds += 1;
      if (stagnantRounds >= 5) break;
    } else {
      stagnantRounds = 0;
    }
    lastHeight = h;
  }

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(200);
}

function buildTurndown() {
  const td = new TurndownService({
    headingStyle: "atx",
    codeBlockStyle: "fenced",
    bulletListMarker: "-",
    emDelimiter: "*",
    strongDelimiter: "**",
  });

  td.addRule("fencedCodeBlock", {
    filter: function (node) {
      return node.nodeName === "PRE";
    },
    replacement: function (content, node) {
      const codeNode = node.querySelector("code");
      const code = (codeNode ? codeNode.textContent : node.textContent) || "";
      const cleaned = code.replace(/\n+$/, "");
      return "\n\n```" + "\n" + cleaned + "\n```" + "\n\n";
    },
  });

  td.addRule("images", {
    filter: "img",
    replacement: function (content, node) {
      const alt = (node.getAttribute("alt") || "").trim();
      const src = (node.getAttribute("src") || "").trim();
      if (!src) return "";
      return `![${alt}](${src})`;
    },
  });

  td.addRule("links", {
    filter: "a",
    replacement: function (content, node) {
      const href = (node.getAttribute("href") || "").trim();
      const text = (content || node.textContent || "").trim() || href;
      if (!href) return text;
      return `[${text}](${href})`;
    },
  });

  td.keep(["table", "thead", "tbody", "tr", "th", "td"]);

  return td;
}

function sanitizeDom(document, baseUrl) {
  const remove = (sel) =>
    document.querySelectorAll(sel).forEach((n) => n.remove());

  remove("script, style, noscript, iframe");
  remove("header nav, footer, .footer, .nav, .navbar, .header, .ads, .advertisement");

  document.querySelectorAll("img").forEach((img) => {
    const candidates = [
      img.getAttribute("data-src"),
      img.getAttribute("data-original"),
      img.getAttribute("data-url"),
      img.getAttribute("data-actualsrc"),
      img.getAttribute("data-lazy-src"),
    ].filter(Boolean);

    if (!img.getAttribute("src") && candidates.length > 0) {
      img.setAttribute("src", candidates[0]);
    }
  });

  const base = (baseUrl || (document && document.baseURI) || "").trim();

  const toAbs = (raw) => {
    const v = (raw || "").trim();
    if (/^(javascript:|mailto:|tel:)/i.test(v)) return v;
    if (v.startsWith("#")) return v;
    try {
      if (!base) return v;
      return new URL(v, base).toString();
    } catch (e) {
      return v;
    }
  };

  document.querySelectorAll("a[href]").forEach((a) => {
    const href = a.getAttribute("href");
    const abs = toAbs(href);
    if (abs && abs !== href) a.setAttribute("href", abs);
  });

  document.querySelectorAll("img[src]").forEach((img) => {
    const src = img.getAttribute("src");
    const abs = toAbs(src);
    if (abs && abs !== src) img.setAttribute("src", abs);
  });
}

function pickFallbackContainerHtml(document) {
  const selectors = [
    "#js_content",
    "article",
    "main",
    "[role=\"main\"]",
    ".content",
    ".post",
    ".entry-content",
    ".article-content",
  ];

  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.textContent && el.textContent.trim().length > 200) {
      return { html: el.innerHTML, selector: sel };
    }
  }

  return {
    html: document.body ? document.body.innerHTML : "",
    selector: "document.body",
  };
}

(async () => {
  // --- GITHUB FAST PATH START ---
  if (url.includes("github.com") && !url.includes("raw.githubusercontent.com")) {
    let rawUrl = url
      .replace("github.com", "raw.githubusercontent.com")
      .replace("/blob/", "/")
      .replace("/tree/", "/");

    let targetUrls = [rawUrl];
    if (!rawUrl.split("/").pop().includes(".")) {
      const base = rawUrl.replace(/\/$/, "");
      targetUrls = [
        `${base}/main/README.md`,
        `${base}/master/README.md`,
        `${base}/main/README.zh-CN.md`,
        `${base}/main/README_zh.md`,
      ];
    }

    for (const u of targetUrls) {
      try {
        const response = await fetch(u, { signal: AbortSignal.timeout(3000) });
        if (response.ok) {
          const text = await response.text();
          console.log("--- METADATA ---");
          console.log(`Title: GitHub Raw - ${url}`);
          console.log(`FinalURL: ${u}`);
          console.log("Extraction: github-raw-fast-path");
          console.log("--- MARKDOWN ---");
          console.log(text);
          process.exit(0);
        }
      } catch (e) {}
    }

    console.error("WARN: GitHub Fast Path failed, falling back to browser mode.");
  }
  // --- GITHUB FAST PATH END ---

  const browser = await chromium.launch({
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-blink-features=AutomationControlled",
    ],
  });

  const context = await browser.newContext({
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    viewport: { width: 1280, height: 800 },
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
  });

  const page = await context.newPage();
  const consoleLogs = [];

  page.on("console", (msg) => {
    try {
      consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
      if (consoleLogs.length > 200) consoleLogs.shift();
    } catch (e) {}
  });

  page.on("pageerror", (err) => {
    consoleLogs.push(
      `[pageerror] ${String(err && err.message ? err.message : err)}`
    );
    if (consoleLogs.length > 200) consoleLogs.shift();
  });

  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(300);

    await waitForStableText(page, {
      minLen: 800,
      stableRounds: 3,
      intervalMs: 700,
      timeoutMs: 30000,
    });

    await smartAutoScroll(page, {
      maxSteps: 40,
      stepPx: 700,
      delayMs: 80,
      maxMs: 12000,
    });

    await waitForStableText(page, {
      minLen: 800,
      stableRounds: 2,
      intervalMs: 600,
      timeoutMs: 15000,
    });

    const html = await page.content();
    const title = await page.title();
    const finalUrl = page.url();

    const dom = new JSDOM(html, { url: finalUrl });
    sanitizeDom(dom.window.document, finalUrl);

    const reader = new Readability(dom.window.document, { keepClasses: false });
    const article = reader.parse();

    let extractedTitle = title || "Untitled";
    let extractedContent = "";
    let extractionMode = "unknown";
    let fallbackSelector = "N/A";

    const turndownService = buildTurndown();

    if (
      article &&
      article.content &&
      article.textContent &&
      article.textContent.trim().length > 200
    ) {
      const at = (article.title || "").trim();
      if (
        at &&
        !at.includes("微信公众平台") &&
        !at.includes("Sina Visitor System")
      ) {
        extractedTitle = at;
      }

      extractedContent = turndownService.turndown(article.content);
      extractionMode = "readability";
    } else {
      console.error(
        "WARN: Readability failed or content too short. Falling back to best container."
      );

      const fb = pickFallbackContainerHtml(dom.window.document);
      fallbackSelector = fb.selector;
      extractedContent = turndownService.turndown(fb.html);
      extractionMode = "fallback-container";

      if (extractedContent.trim().length < 200) {
        console.error(
          "WARN: Fallback container content too short. Falling back to body innerText."
        );
        extractedContent = await page.evaluate(() =>
          document.body ? document.body.innerText : ""
        );
        extractionMode = "body-innerText";
      }
    }

    if (extractedContent.trim().length < 200) {
      const info = {
        inputUrl: url,
        finalUrl: page.url(),
        pageTitle: await page.title(),
        contentLength: extractedContent.length,
        extractionMode,
        fallbackSelector,
        ts: nowIso(),
      };

      console.error(
        "WARN: Unreliable result after extraction. Debug Info:",
        JSON.stringify(info)
      );

      try {
        const screenshotPath = `/tmp/scrape-fail-${info.ts}.png`;
        await page.screenshot({ path: screenshotPath, fullPage: true });
        console.error(`DEBUG: Saved screenshot: ${screenshotPath}`);
      } catch (e) {
        console.error(`DEBUG: Could not save screenshot: ${e.message}`);
      }

      if (consoleLogs.length > 0) {
        console.error("DEBUG: Recent page console logs:");
        console.error(consoleLogs.slice(-30).join("\n"));
      }

      throw new Error("Scraping failed to get meaningful content.");
    }

    console.log("--- METADATA ---");
    console.log(`Title: ${extractedTitle}`);
    console.log(`Author: ${article ? article.byline || "N/A" : "N/A"}`);
    console.log(`Site: ${article ? article.siteName || "N/A" : "N/A"}`);
    console.log(`FinalURL: ${page.url()}`);
    console.log(`Extraction: ${extractionMode}`);
    if (extractionMode !== "readability") {
      console.log(`FallbackSelector: ${fallbackSelector}`);
    }
    console.log("--- MARKDOWN ---");
    console.log(extractedContent);
  } catch (error) {
    console.error(`ERROR: Scrape operation failed: ${error.message}`);
    try {
      const finalUrl = page.url();
      const pageTitle = await page.title();
      console.error(
        `DEBUG: Current URL: ${finalUrl}, Page Title: ${pageTitle}`
      );
    } catch (e) {
      console.error(
        `DEBUG: Could not get current URL or page title after error: ${e.message}`
      );
    }
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
