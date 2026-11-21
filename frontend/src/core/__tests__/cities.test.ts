// @vitest-environment jsdom
/** 城市解析：只认内置列表，其他值一律回落默认城市。 */

import { describe, expect, it } from 'vitest'
import { CITIES, DEFAULT_CITY, resolveCity } from '../cities'

describe('resolveCity', () => {
  it('列表内的值原样返回', () => {
    expect(resolveCity('上海')).toBe('上海')
    expect(resolveCity('武汉')).toBe('武汉')
    expect(CITIES).toHaveLength(8)
  })

  it('空值返回默认城市', () => {
    expect(resolveCity(null)).toBe(DEFAULT_CITY)
    expect(resolveCity(undefined)).toBe(DEFAULT_CITY)
    expect(resolveCity('')).toBe(DEFAULT_CITY)
  })

  it('表外的值也回落默认城市，不抛错', () => {
    expect(resolveCity('纽约')).toBe('杭州')
    expect(resolveCity(' 上海 ')).toBe('杭州')
    expect(resolveCity('hangzhou')).toBe('杭州')
  })
})
