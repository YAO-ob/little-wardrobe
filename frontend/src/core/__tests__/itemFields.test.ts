// @vitest-environment jsdom
/** 字段可见性矩阵。 */

import { describe, expect, it } from 'vitest'
import { isIncomplete, visibleFields } from '../itemFields'
import type { Category } from '../types'

const ALL: Category[] = ['top', 'outer', 'bottom', 'shoes', 'accessory', 'dress']

describe('visibleFields', () => {
  it('配饰不含 warmth / layer / season / size / care_symbols', () => {
    const fields = visibleFields('accessory')
    for (const key of ['warmth', 'layer', 'season', 'size', 'care_symbols'] as const) {
      expect(fields.has(key)).toBe(false)
    }
    expect(fields.has('material')).toBe(true)
  })

  it('鞋含 material / size，但不含 layer / care_symbols', () => {
    const fields = visibleFields('shoes')
    expect(fields.has('material')).toBe(true)
    expect(fields.has('size')).toBe(true)
    expect(fields.has('layer')).toBe(false)
    expect(fields.has('care_symbols')).toBe(false)
  })

  it('上衣含 layer 与 care_symbols', () => {
    const fields = visibleFields('top')
    expect(fields.has('layer')).toBe(true)
    expect(fields.has('care_symbols')).toBe(true)
  })

  it('layer 只在 top / outer 出现', () => {
    for (const category of ALL) {
      expect(visibleFields(category).has('layer')).toBe(category === 'top' || category === 'outer')
    }
  })
})

describe('isIncomplete', () => {
  const complete = {
    category: 'top' as Category,
    color_family: '黑',
    occasion: 'casual' as const,
    warmth: 2 as const,
  }

  it('核心字段齐全 → 不标红', () => {
    expect(isIncomplete(complete)).toBe(false)
  })

  it('缺颜色 → 标红', () => {
    expect(isIncomplete({ ...complete, color_family: '' })).toBe(true)
    expect(isIncomplete({ ...complete, color_family: null })).toBe(true)
  })

  it('缺场合 → 标红', () => {
    expect(isIncomplete({ ...complete, occasion: null })).toBe(true)
  })

  it('上衣缺厚薄 → 标红', () => {
    expect(isIncomplete({ ...complete, warmth: null })).toBe(true)
  })

  it('配饰缺厚薄不算不全（配饰本来就没厚薄）', () => {
    expect(isIncomplete({ ...complete, category: 'accessory', warmth: null })).toBe(false)
  })

  it('配饰只要颜色和场合齐了就完整', () => {
    expect(isIncomplete({ category: 'accessory', color_family: '黑', occasion: 'sport', warmth: null })).toBe(false)
  })
})
