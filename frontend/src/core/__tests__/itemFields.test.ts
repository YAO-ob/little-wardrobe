// @vitest-environment jsdom
/** 字段可见性矩阵。 */

import { describe, expect, it } from 'vitest'
import { visibleFields } from '../itemFields'
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
