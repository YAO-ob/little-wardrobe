// @vitest-environment jsdom
/** 徽标与降级文案：纯逻辑，钉住「AI / 缓存 / 规则」三种状态。 */

import { describe, expect, it } from 'vitest'
import { badgeFor, fallbackText, maskKey } from '../recommendBadge'

describe('badgeFor', () => {
  it('模型成功 → AI 精选', () => {
    expect(badgeFor({ source: 'llm', cached: false, fallback_reason: null })).toEqual({
      label: 'AI 精选',
      tone: 'ai',
      detail: null,
    })
  })

  it('模型成功但命中缓存 → AI 精选 · 缓存', () => {
    expect(badgeFor({ source: 'llm', cached: true, fallback_reason: null })).toEqual({
      label: 'AI 精选 · 缓存',
      tone: 'cache',
      detail: null,
    })
  })

  it('降级 → 规则推荐 + 可读原因', () => {
    const badge = badgeFor({ source: 'rules', cached: false, fallback_reason: 'no_key' })
    expect(badge.label).toBe('规则推荐')
    expect(badge.tone).toBe('rules')
    expect(badge.detail).toBe('没有配置 API key')
  })

  it('纯规则（没有降级原因）→ 规则推荐、无说明', () => {
    expect(badgeFor({ source: 'rules', cached: false, fallback_reason: null }).detail).toBeNull()
  })
})

describe('fallbackText', () => {
  it.each([
    ['rate_limited', '请求太频繁，稍后再试'],
    ['timeout', '模型响应超时'],
    ['invalid_ids', '模型给的单品不在候选里'],
    ['truncated', '模型输出被截断'],
    ['missing_category', '衣橱里缺基础品类'],
  ])('%s → %s', (reason, text) => {
    expect(fallbackText(reason)).toBe(text)
  })

  it('未知原因给兜底文案，不返回空', () => {
    expect(fallbackText('something_new')).toBe('模型暂时不可用')
    expect(fallbackText(null)).toBeNull()
  })
})

describe('maskKey', () => {
  it('保留前三位，其余打码', () => {
    expect(maskKey('sk-1234567890abcdef')).toBe('sk-****')
  })

  it('太短就全打码，空串返回空', () => {
    expect(maskKey('short')).toBe('****')
    expect(maskKey('   ')).toBe('')
  })
})
