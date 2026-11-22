// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { fallbackHint } from '../chatFallback'

describe('fallbackHint', () => {
  it('已知原因给对应文案', () => {
    expect(fallbackHint('no_key')).toBe('没配置 API key，用的是规则推荐')
    expect(fallbackHint('rate_limited')).toBe('请求太频繁，暂时用规则推荐')
    expect(fallbackHint('invalid_ids')).toBe('模型这次没挑对，用了规则推荐')
    expect(fallbackHint('timeout')).toBe('模型超时，用了规则推荐')
  })

  it('没有原因或未知原因返回 null（不显示）', () => {
    expect(fallbackHint(null)).toBeNull()
    expect(fallbackHint(undefined)).toBeNull()
    expect(fallbackHint('')).toBeNull()
    expect(fallbackHint('something_else')).toBeNull()
  })
})
