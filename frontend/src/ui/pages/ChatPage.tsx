import { useEffect, useRef, useState } from 'react'
import { sendChat } from '../../core/api'
import { useChatStore } from '../../core/chatStore'
import { makeDraftId } from '../../core/drafts'
import { FALLBACK_CITIES } from '../../core/cities'
import { getCity } from '../../adapters/city'
import { getLlmKey } from '../../adapters/llmKey'
import type { ChatMessage } from '../../core/chatStore'
import OutfitCard from '../components/OutfitCard'

const EXAMPLES = ['我晚点要约会', '上班穿什么', '今天天气怎么样']

export default function ChatPage() {
  const messages = useChatStore((state) => state.messages)
  const append = useChatStore((state) => state.append)
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, sending])

  async function ask(text: string, options: { excludeIds?: number[]; echo?: boolean } = {}) {
    const trimmed = text.trim()
    if (!trimmed || sending) return

    if (options.echo !== false) {
      append({ id: makeDraftId(), role: 'user', text: trimmed })
    }
    setSending(true)
    try {
      const key = getLlmKey()
      const reply = await sendChat({
        message: trimmed,
        city: getCity(FALLBACK_CITIES),
        excludeIds: options.excludeIds,
        mode: key ? 'llm' : 'rules',
        llmKey: key || undefined,
      })
      append({
        id: makeDraftId(),
        role: 'agent',
        text: reply.reply,
        intent: reply.intent,
        trace: reply.trace,
        outfits: reply.outfits,
      })
    } catch (err) {
      append({
        id: makeDraftId(),
        role: 'agent',
        text: err instanceof Error ? err.message : '请求失败',
        failed: true,
        retryText: trimmed,
      })
    } finally {
      setSending(false)
    }
  }

  function reroll(message: ChatMessage) {
    const first = message.outfits?.[0]
    if (!first) return
    void ask('换一套', { excludeIds: first.items.map((item) => item.id) })
  }

  return (
    <div className="pb-24">
      {messages.length === 0 ? (
        <div className="space-y-3 pt-8 text-center">
          <p className="text-3xl">💬</p>
          <p className="text-sm text-black/50">想怎么穿，直接问</p>
          <div className="flex flex-wrap justify-center gap-2 pt-2">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => void ask(example)}
                className="rounded-full border border-black/10 bg-white px-3 py-1.5 text-xs text-black/60"
              >
                {example}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] space-y-2 ${
                  message.role === 'user'
                    ? 'rounded-2xl rounded-br-sm bg-black px-3 py-2 text-sm text-white'
                    : 'w-full'
                }`}
              >
                {message.role === 'agent' ? (
                  <div className="space-y-2">
                    <div
                      className={`inline-block rounded-2xl rounded-bl-sm px-3 py-2 text-sm ${
                        message.failed ? 'bg-red-50 text-red-700' : 'bg-white text-black/80 shadow-sm'
                      }`}
                    >
                      {message.text}
                    </div>

                    {message.failed && message.retryText && (
                      <button
                        type="button"
                        onClick={() => void ask(message.retryText!, { echo: false })}
                        disabled={sending}
                        className="rounded-xl border border-black/10 bg-white px-3 py-1.5 text-xs text-black/60 disabled:opacity-40"
                      >
                        重试
                      </button>
                    )}

                    {message.trace && message.trace.length > 0 && (
                      <details className="rounded-xl bg-white/70 px-3 py-2 text-[11px] text-black/50 shadow-sm">
                        <summary className="cursor-pointer select-none">
                          执行了 {message.trace.length} 步 ▾
                        </summary>
                        <ul className="mt-1.5 space-y-1">
                          {message.trace.map((step, index) => (
                            <li key={`${step.tool}-${index}`} className="tabular-nums">
                              {step.tool} · {step.summary} · {step.ms}ms
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}

                    {message.outfits && message.outfits.length > 0 && (
                      <div className="space-y-2">
                        {message.outfits.map((outfit, index) => (
                          <OutfitCard key={index} outfit={outfit} />
                        ))}
                        <button
                          type="button"
                          onClick={() => reroll(message)}
                          disabled={sending}
                          className="w-full rounded-xl border border-black/10 bg-white py-2 text-sm text-black/60 disabled:opacity-40"
                        >
                          {sending ? '换一套中…' : '换一套'}
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  message.text
                )}
              </div>
            </div>
          ))}
          {sending && (
            <p className="pl-1 text-[11px] text-black/40">正在挑…</p>
          )}
          <div ref={endRef} />
        </div>
      )}

      <div className="fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-20 mx-auto max-w-xl border-t border-black/5 bg-paper/95 px-3 py-2 backdrop-blur">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                void ask(input)
                setInput('')
              }
            }}
            placeholder="问点什么，比如「明天上班穿什么」"
            disabled={sending}
            className="flex-1 rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-black/30 disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => {
              void ask(input)
              setInput('')
            }}
            disabled={sending || input.trim() === ''}
            className="rounded-xl bg-black px-4 py-2 text-sm text-white disabled:opacity-40"
          >
            {sending ? '挑…' : '发送'}
          </button>
        </div>
      </div>
    </div>
  )
}
