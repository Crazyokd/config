#!/usr/bin/env node
"use strict";

const http = require("http");
const { spawn } = require("child_process");

const nodeBin = process.env.NODE_BIN || process.execPath;
const controlPlaneCli = process.env.HINDSIGHT_CONTROL_PLANE_CLI;
const apiUrl =
  process.env.HINDSIGHT_CP_DATAPLANE_API_URL || "http://127.0.0.1:8888";
const listenHost = process.env.HINDSIGHT_CP_HOSTNAME || "127.0.0.1";
const listenPort = Number.parseInt(process.env.HINDSIGHT_CP_PORT || "9999", 10);
const internalHost = process.env.HINDSIGHT_CP_INTERNAL_HOST || "127.0.0.1";
const internalPort = Number.parseInt(
  process.env.HINDSIGHT_CP_INTERNAL_PORT || String(listenPort + 1),
  10,
);
const defaultLocale = process.env.HINDSIGHT_CP_DEFAULT_LOCALE || "zh-CN";
const knownLocales = new Set(["zh-CN", "en"]);

if (!controlPlaneCli) {
  console.error("HINDSIGHT_CONTROL_PLANE_CLI is required");
  process.exit(1);
}

const child = spawn(
  nodeBin,
  [
    controlPlaneCli,
    "--api-url",
    apiUrl,
    "--hostname",
    internalHost,
    "--port",
    String(internalPort),
  ],
  {
    env: {
      ...process.env,
      HOSTNAME: internalHost,
      PORT: String(internalPort),
    },
    stdio: "inherit",
  },
);

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

function firstPathSegment(pathname) {
  return pathname.split("/")[1] || "";
}

function cookieLocale(req) {
  const cookie = req.headers.cookie || "";
  for (const part of cookie.split(";")) {
    const [rawName, ...rawValue] = part.trim().split("=");
    if (rawName !== "NEXT_LOCALE") {
      continue;
    }
    const value = decodeURIComponent(rawValue.join("="));
    if (knownLocales.has(value)) {
      return value;
    }
  }
  return null;
}

function refererLocale(req) {
  const referer = req.headers.referer;
  if (!referer) {
    return null;
  }

  try {
    const refererUrl = new URL(referer);
    const locale = firstPathSegment(refererUrl.pathname);
    return knownLocales.has(locale) ? locale : null;
  } catch {
    return null;
  }
}

function acceptLanguageLocale(req) {
  const acceptLanguage = req.headers["accept-language"] || "";
  if (acceptLanguage.toLowerCase().includes("zh")) {
    return "zh-CN";
  }
  if (acceptLanguage.toLowerCase().includes("en")) {
    return "en";
  }
  return null;
}

function preferredLocale(req) {
  return (
    cookieLocale(req) ||
    refererLocale(req) ||
    acceptLanguageLocale(req) ||
    defaultLocale
  );
}

function localeRedirectPath(req, pathname) {
  if (pathname === "/") {
    return `/${preferredLocale(req)}/dashboard`;
  }

  const firstSegment = firstPathSegment(pathname);
  if (
    firstSegment === "api" ||
    firstSegment === "_next" ||
    firstSegment === "_vercel" ||
    knownLocales.has(firstSegment) ||
    /\.[^/]+$/.test(pathname)
  ) {
    return null;
  }

  return `/${preferredLocale(req)}${pathname}`;
}

function localeForPath(pathname) {
  const locale = firstPathSegment(pathname);
  return knownLocales.has(locale) ? locale : null;
}

function appendLocaleCookie(headers, locale) {
  if (!locale) {
    return headers;
  }

  const cookie = `NEXT_LOCALE=${encodeURIComponent(locale)}; Path=/; SameSite=Lax`;
  const nextHeaders = { ...headers };
  const existing = nextHeaders["set-cookie"];
  if (!existing) {
    nextHeaders["set-cookie"] = cookie;
  } else if (Array.isArray(existing)) {
    nextHeaders["set-cookie"] = [...existing, cookie];
  } else {
    nextHeaders["set-cookie"] = [existing, cookie];
  }
  return nextHeaders;
}

function proxyRequest(req, res) {
  const requestUrl = new URL(req.url || "/", `http://${req.headers.host || ""}`);
  const currentLocale = localeForPath(requestUrl.pathname);
  const headers = { ...req.headers, host: `${internalHost}:${internalPort}` };
  const upstreamReq = http.request(
    {
      hostname: internalHost,
      port: internalPort,
      method: req.method,
      path: req.url,
      headers,
    },
    (upstreamRes) => {
      res.writeHead(
        upstreamRes.statusCode || 502,
        appendLocaleCookie(upstreamRes.headers, currentLocale),
      );
      upstreamRes.pipe(res);
    },
  );

  upstreamReq.on("error", () => {
    if (!res.headersSent) {
      res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    }
    res.end("hindsight control plane upstream unavailable\n");
  });

  req.pipe(upstreamReq);
}

const server = http.createServer((req, res) => {
  const requestUrl = new URL(req.url || "/", `http://${req.headers.host || ""}`);
  const redirectPath = localeRedirectPath(req, requestUrl.pathname);
  if (redirectPath) {
    const locale = firstPathSegment(redirectPath);
    res.writeHead(307, {
      location: `${redirectPath}${requestUrl.search}`,
      "set-cookie": `NEXT_LOCALE=${encodeURIComponent(locale)}; Path=/; SameSite=Lax`,
    });
    res.end();
    return;
  }

  proxyRequest(req, res);
});

function shutdown(signal) {
  server.close(() => undefined);
  if (!child.killed) {
    child.kill(signal);
  }
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

server.listen(listenPort, listenHost, () => {
  console.log(
    `hindsight control plane proxy listening on http://${listenHost}:${listenPort}, upstream http://${internalHost}:${internalPort}`,
  );
});
