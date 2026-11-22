// @vitest-environment jsdom
/** 对话历史：只测 append / clear，状态本身不持久化。 */

import { beforeEach, describe, expect, it } from 'vitest'
import { useChatStore } from '../chatStore'

describe('chatStore', () => {
  beforeEach(() => {
    useChatStore.getState().clear()
  })

  it('append 累积消息，顺序保持', () => {
    const { append } = useChatStore.getState()
    append({ id: '1', role: 'user', text: '我晚点要约会' })
    append({ id: '2', role: 'agent', text: '正在挑', trace: [], outfits: [] })

    const messages = useChatStore.getState().messages
    expect(messages.map((message) => message.role)).toEqual(['user', 'agent'])
    expect(messages[1].text).toBe('正在挑')
  })

  it('clear 清空', () => {
    useChatStore.getState().append({ id: '1', role: 'user', text: 'hi' })
    useChatStore.getState().clear()
    expect(useChatStore.getState().messages).toEqual([])
  })
})
