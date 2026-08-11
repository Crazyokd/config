/**
 * Hindsight memory hooks for opencode.
 *
 * 迁移自 Codex 的 ~/.codex/hooks/hindsight_codex.py：
 * - UserPromptSubmit → recall：用户提交新消息时，用 Hindsight 记忆增强上下文。
 * - Stop → retain：会话结束后，把最近一轮对话写回 Hindsight。
 *
 * 使用全局 Hindsight daemon（http://127.0.0.1:8888），bank 与 Codex 共用
 * （hermes-unified），保证两个 agent 的记忆互通。
 */

import type { Plugin } from "@opencode-ai/plugin"

const HINDSIGHT_API_URL = process.env.HINDSIGHT_API_URL || "http://127.0.0.1:8888"
const HINDSIGHT_BANK_ID = process.env.HINDSIGHT_BANK_ID || "hermes-unified"
const HINDSIGHT_TIMEOUT_MS = Number(process.env.HINDSIGHT_REQUEST_TIMEOUT_SECONDS || 20) * 1000

// 每个 session 记住最近一次 recall 的 messageID，避免同一消息重复 recall。
const lastRecall = new Map<string, string>()
const seenTurns = new Map<string, Set<string>>()

async function hindsightRequest(path: string, body: unknown): Promise<any | null> {
  const url = `${HINDSIGHT_API_URL}${path}`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), HINDSIGHT_TIMEOUT_MS)
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "User-Agent": "hindsight-opencode" },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (!response.ok) {
      const detail = await response.text()
      throw new Error(`HTTP ${response.status}: ${detail}`)
    }
    return await response.json()
  } finally {
    clearTimeout(timer)
  }
}

function deriveBankId(cwd: string): string {
  // Codex 的 bank.py derive_bank_id：静态模式直接返回 bankId（HINDSIGHT_BANK_ID）。
  // 为与 Codex 记忆互通，沿用静态 bank，不再按目录派生。
  return HINDSIGHT_BANK_ID
}

function formatMemories(results: Array<any>): string {
  if (!results || results.length === 0) return ""
  const lines = results.map((r) => {
    const text = r?.text || ""
    const memType = r?.type || ""
    const mentionedAt = r?.mentioned_at || ""
    return `- ${text}${memType ? ` [${memType}]` : ""}${mentionedAt ? ` (${mentionedAt})` : ""}`
  })
  return lines.join("\n\n")
}

function formatCurrentTime(): string {
  return new Date().toISOString().replace(/\.\d+Z$/, "").replace("T", " ").concat(" UTC")
}

function extractUserText(parts: any[]): string {
  const text = parts
    .filter((p) => p?.type === "text" && typeof p.text === "string")
    .map((p) => p.text)
    .join("\n")
    .trim()
  if (text.startsWith("# AGENTS.md instructions")) return ""
  if (text.startsWith("<environment_context>")) return ""
  return text
}

async function recall(prompt: string): Promise<string> {
  const bankId = deriveBankId("")
  const path = `/v1/default/banks/${encodeURIComponent(bankId)}/memories/recall`
  const response = await hindsightRequest(path, {
    query: prompt.slice(0, 800),
    max_tokens: 1024,
    budget: "mid",
  })
  if (!response) return ""
  const results = response.results || []
  const memories = formatMemories(results)
  if (!memories) return ""
  return `<hindsight_memories>\nCurrent time - ${formatCurrentTime()}\n\n${memories}\n</hindsight_memories>`
}

async function retain(sessionID: string, messages: any[]): Promise<void> {
  if (!messages || messages.length === 0) return

  // 只保留最后一个 user 轮次之后的对话（对齐 Codex slice_last_turns_by_user_boundary）。
  const lastUserIdx = messages.map((m) => m.role).lastIndexOf("user")
  const turns = lastUserIdx >= 0 ? messages.slice(lastUserIdx) : messages.slice(-4)
  if (turns.length === 0) return

  const content = turns
    .map((m) => `${m.role}: ${Array.isArray(m.content) ? m.content.map((p: any) => p?.text || "").join("") : m.content}`)
    .join("\n")
    .trim()
  if (!content) return

  const bankId = deriveBankId("")
  const path = `/v1/default/banks/${encodeURIComponent(bankId)}/memories`
  const now = new Date().toISOString()
  await hindsightRequest(path, {
    items: [
      {
        content: `# opencode hook transcript retained for Hindsight\n${JSON.stringify({
          session_id: sessionID,
          cwd: "",
          model: "",
          message_count: turns.length,
          retention_policy: "last_opencode_turn",
        })}\n\n${content}`,
        document_id: `opencode:${sessionID}:${now}`,
        context: "opencode-hook",
        metadata: {
          retained_at: now,
          message_count: String(turns.length),
          session_id: sessionID,
          source: "opencode-hook",
        },
        tags: ["opencode", "opencode-hook", sessionID],
      },
    ],
    async: true,
  })
}

export const HindsightHooksPlugin: Plugin = async ({ client }) => {
  return {
    // 对齐 Codex UserPromptSubmit recall：在用户消息提交后、生成前增强上下文。
    "chat.message": async (input, output) => {
      const sessionID = input.sessionID
      const messageID = input.messageID || ""
      if (lastRecall.get(sessionID) === messageID) return
      const prompt = extractUserText(output.parts)
      if (prompt.length < 5) return
      try {
        const context = await recall(prompt)
        if (context) {
          // 追加到用户消息文本前，让模型在生成时看到记忆。
          const firstText = output.parts.find((p) => p.type === "text")
          if (firstText) {
            ;(firstText as any).text = `${context}\n\n${(firstText as any).text}`
          }
          lastRecall.set(sessionID, messageID)
        }
      } catch (err) {
        console.error(`[Hindsight] Recall failed: ${(err as Error).message}`)
      }
    },

    // 对齐 Codex Stop retain：会话空闲时把最后一轮写回 Hindsight。
    event: async ({ event }) => {
      const type = event?.type || ""
      if (type !== "session.idle" && type !== "message.updated") return
      const sessionID = (event as any)?.properties?.sessionID
      if (!sessionID) return

      const info = (event as any)?.properties?.info
      const messageID = info?.id
      const role = info?.role
      const isAssistantFinished = type === "message.updated" && role === "assistant" && !!info?.finish
      if (!isAssistantFinished) return

      const key = `${sessionID}:${messageID}`
      const seen = seenTurns.get(sessionID) || new Set<string>()
      if (seen.has(key)) return
      seen.add(key)
      seenTurns.set(sessionID, seen)

      try {
        const res: any = await client.session.messages({ path: { id: sessionID } })
        const messages = Array.isArray(res) ? res : res?.data
        if (Array.isArray(messages) && messages.length > 0) {
          const mapped = messages.map((m: any) => {
            const infoMsg = m?.info || m
            return {
              role: infoMsg?.role || "unknown",
              content: Array.isArray(m?.parts)
                ? m.parts.map((p: any) => p?.text || "").join("\n")
                : "",
            }
          })
          await retain(sessionID, mapped)
        }
      } catch (err) {
        console.error(`[Hindsight] Retain failed: ${(err as Error).message}`)
      }
    },
  }
}
