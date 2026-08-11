#!/usr/bin/env node
/**
 * MCP 公共规范生成器
 *
 * 读取 ./mcp-servers.json（单一真源），产出三套 agent 的 MCP 配置片段：
 *   - codex：    ~/.codex/config.toml 的 [mcp_servers.*] 块
 *   - claude：   ~/.claude.json 的 mcpServers 对象片段
 *   - opencode： ~/.config/opencode/ 的 mcp 对象片段
 *
 * 用法：node generate.mjs [--home /path/to/home] [--out-dir dir]
 * 默认把结果写到 ./out/ 下，不直接改各 agent 配置（由 install.sh 做合并）。
 */

import { readFileSync, mkdirSync, writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const HERE = dirname(fileURLToPath(import.meta.url))
const HOME = process.env.HOME || ""

const argv = process.argv.slice(2)
const homeArg = argv.find((a) => a.startsWith("--home="))
const outArg = argv.find((a) => a.startsWith("--out-dir="))
const userHome = homeArg ? homeArg.split("=")[1] : HOME
const outDir = outArg ? resolve(outArg) : resolve(HERE, "out")

const doc = JSON.parse(readFileSync(resolve(HERE, "mcp-servers.json"), "utf8"))
const servers = doc.servers

function resolveVars(value) {
  if (typeof value !== "string") return value
  return value.replace(/\{home\}/g, userHome)
}

/** 展开一个 server 的 command/args/env 为已解析的普通对象 */
function normalize(name, srv) {
  return {
    name,
    command: resolveVars(srv.command),
    args: (srv.args || []).map(resolveVars),
    env: Object.fromEntries(Object.entries(srv.env || {}).map(([k, v]) => [k, resolveVars(v)])),
    enabled: srv.enabled !== false,
  }
}

/** 过滤掉值含 {env:} 的 env 项——它们留给 opencode 展开，codex/claude 靠脚本默认值 */
function envWithoutEnvRefs(env) {
  return Object.fromEntries(Object.entries(env).filter(([, v]) => typeof v !== "string" || !v.includes("{env:")))
}

/** ---------- codex (TOML) ---------- */
function toCodex(server) {
  const lines = []
  const { name, command, args, env } = server
  const envClean = envWithoutEnvRefs(env)
  lines.push(`[mcp_servers.${name}]`)
  lines.push(`command = ${JSON.stringify(command)}`)
  if (args.length) {
    const arr = args.map((a) => JSON.stringify(a)).join(", ")
    lines.push(`args = [${arr}]`)
  }
  if (!server.enabled) lines.push(`enabled = false`)
  if (Object.keys(envClean).length) {
    lines.push(`[mcp_servers.${name}.env]`)
    for (const [k, v] of Object.entries(envClean)) lines.push(`${k} = ${JSON.stringify(v)}`)
  }
  return lines.join("\n")
}

/** ---------- claude (mcpServers JSON fragment) ---------- */
function toClaude(server) {
  const { name, command, args, env } = server
  const envClean = envWithoutEnvRefs(env)
  const obj = { type: "stdio", command }
  if (args.length) obj.args = args
  if (Object.keys(envClean).length) obj.env = envClean
  if (!server.enabled) obj.enabled = false
  return { [name]: obj }
}

/** ---------- opencode (mcp JSON fragment) ---------- */
function toOpencode(server) {
  const { name, command, args, env } = server
  const obj = {
    type: "local",
    command: [command, ...args],
    enabled: server.enabled,
  }
  if (Object.keys(env).length) obj.environment = env
  return { [name]: obj }
}

// 产出三套
const claudeObj = {}
const opencodeObj = {}
const codexParts = []
for (const [name, srv] of Object.entries(servers)) {
  const n = normalize(name, srv)
  codexParts.push(toCodex(n))
  Object.assign(claudeObj, toClaude(n))
  Object.assign(opencodeObj, toOpencode(n))
}

const codexBlock = codexParts.join("\n\n")
const claudeJson = JSON.stringify(claudeObj, null, 2)
const opencodeJson = JSON.stringify(opencodeObj, null, 2)

mkdirSync(outDir, { recursive: true })
writeFileSync(resolve(outDir, "codex-mcp.toml"), codexBlock + "\n")
writeFileSync(resolve(outDir, "claude-mcp.json"), claudeJson + "\n")
writeFileSync(resolve(outDir, "opencode-mcp.json"), opencodeJson + "\n")

console.log("==> 已生成 MCP 配置片段:")
console.log(`    ${outDir}/codex-mcp.toml`)
console.log(`    ${outDir}/claude-mcp.json`)
console.log(`    ${outDir}/opencode-mcp.json`)
console.log(`    (home 解析为 ${userHome})`)
