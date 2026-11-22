/** 对话历史：跨 tab 状态，所以放 zustand；刷新即清空（不持久化）。 */

import { create } from 'zustand'
import type { ChatTraceStep, RecommendOutfit } from './types'

export interface ChatMessage {
  id: string
  role: 'user' | 'agent'
  text: string
  intent?: string
  trace?: ChatTraceStep[]
  outfits?: RecommendOutfit[]
  /** 出错时保留原文，供「重试」用 */
  retryText?: string
  failed?: boolean
  /** 后端降级原因（no_key / rate_limited / invalid_ids …），用于气泡下方小字 */
  reason?: string | null
}

interface ChatState {
  messages: ChatMessage[]
  append: (message: ChatMessage) => void
  clear: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  append: (message) => set((state) => ({ messages: [...state.messages, message] })),
  clear: () => set({ messages: [] }),
}))
