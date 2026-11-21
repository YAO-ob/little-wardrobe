// @vitest-environment jsdom
/** 城市解析：只认给定列表，其他值一律回落默认城市。 */

import { describe, expect, it } from 'vitest'
import { DEFAULT_CITY, FALLBACK_CITIES, resolveCity } from '../cities'

describe('resolveCity', () => {
  it('列表内的值原样返回', () => {
    expect(resolveCity('上海', FALLBACK_CITIES)).toBe('上海')
    expect(resolveCity('武汉', FALLBACK_CITIES)).toBe('武汉')
    expect(FALLBACK_CITIES).toHaveLength(8)
  })

  it('空值返回默认城市', () => {
    expect(resolveCity(null, FALLBACK_CITIES)).toBe(DEFAULT_CITY)
    expect(resolveCity(undefined, FALLBACK_CITIES)).toBe(DEFAULT_CITY)
    expect(resolveCity('', FALLBACK_CITIES)).toBe(DEFAULT_CITY)
  })

  it('不在给定列表里也回落默认城市（后端加了新城市时以接口列表为准）', () => {
    expect(resolveCity('纽约', FALLBACK_CITIES)).toBe('杭州')
    expect(resolveCity(' 上海 ', FALLBACK_CITIES)).toBe('杭州')
    expect(resolveCity('测试城', ['测试城', '杭州'])).toBe('测试城')
  })
})
