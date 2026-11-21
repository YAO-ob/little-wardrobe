// @vitest-environment jsdom
/** 天气快照的「多久以前」文案。 */

import { describe, expect, it } from 'vitest'
import { weatherAgeText } from '../weatherAge'

const NOW = Date.parse('2026-11-22T00:00:00+08:00')

describe('weatherAgeText', () => {
  it('不到 1 小时 → 不到 1 小时前', () => {
    const fetched = new Date(NOW - 30 * 60 * 1000).toISOString()
    expect(weatherAgeText(fetched, NOW)).toBe('不到 1 小时前')
  })

  it('超过 1 小时 → N 小时前（四舍五入）', () => {
    const threeHours = new Date(NOW - 3 * 3600 * 1000).toISOString()
    expect(weatherAgeText(threeHours, NOW)).toBe('3 小时前')

    const threeAndHalf = new Date(NOW - 3.5 * 3600 * 1000).toISOString()
    expect(weatherAgeText(threeAndHalf, NOW)).toBe('4 小时前')
  })

  it('缺失或非法时间 → 较早的缓存', () => {
    expect(weatherAgeText(null, NOW)).toBe('较早的缓存')
    expect(weatherAgeText('', NOW)).toBe('较早的缓存')
    expect(weatherAgeText('not-a-date', NOW)).toBe('较早的缓存')
  })
})
