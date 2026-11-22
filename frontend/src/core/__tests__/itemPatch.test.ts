// @vitest-environment jsdom
/** 表单 → PATCH body：空串转 null、没动的字段不进 body。 */

import { describe, expect, it } from 'vitest'
import { buildItemPatch, validateItemForm, type ItemFormValues } from '../itemPatch'
import type { Item } from '../types'

const baseItem: Item = {
  id: 7,
  name: '上衣',
  category: 'top',
  season: ['spring'],
  images: [],
  color_family: '黑',
  brand: null,
  material: null,
  formality: null,
  layer: null,
  price: 100,
  note: null,
}

function form(overrides: Partial<ItemFormValues> = {}): ItemFormValues {
  return {
    color_family: '黑',
    brand: '',
    material: '',
    formality: '',
    layer: '',
    season: ['spring'],
    price: '100',
    note: '',
    size: '',
    purchase_url: '',
    care_text: '',
    care_symbols: [],
    ...overrides,
  }
}

describe('buildItemPatch', () => {
  it('没改任何字段时返回空对象', () => {
    expect(buildItemPatch(form(), baseItem)).toEqual({})
  })

  it('清空字段发 null，而不是空字符串', () => {
    const patch = buildItemPatch(form({ color_family: '  ' }), baseItem)
    expect(patch).toEqual({ color_family: null })
  })

  it('只包含改过的字段，并做类型转换', () => {
    const patch = buildItemPatch(
      form({
        color_family: '藏青',
        brand: '测试牌',
        formality: '4',
        layer: 'inner',
        season: ['spring', 'autumn'],
        price: '199.5',
        size: 'M',
        purchase_url: 'https://example.com/p/1',
        care_text: '30℃ 机洗',
        care_symbols: ['wash_30', 'no_bleach'],
      }),
      baseItem,
    )

    expect(patch).toEqual({
      color_family: '藏青',
      brand: '测试牌',
      formality: 4,
      layer: 'inner',
      season: ['spring', 'autumn'],
      price: 199.5,
      size: 'M',
      purchase_url: 'https://example.com/p/1',
      care_text: '30℃ 机洗',
      care_symbols: ['wash_30', 'no_bleach'],
    })
    expect('material' in patch).toBe(false)
    expect('note' in patch).toBe(false)
  })

  it('洗护符号没变时不出现在 patch 里', () => {
    const withCare: Item = { ...baseItem, care_symbols: ['wash_30'] }
    const patch = buildItemPatch(form({ care_symbols: ['wash_30'] }), withCare)
    expect('care_symbols' in patch).toBe(false)

    const changed = buildItemPatch(form({ care_symbols: ['no_bleach'] }), withCare)
    expect(changed.care_symbols).toEqual(['no_bleach'])
  })
})

describe('validateItemForm', () => {
  it('价格不是数字时提示', () => {
    expect(validateItemForm(form({ price: 'abc' }))).toEqual({ price: '价格要填不小于 0 的数字' })
    expect(validateItemForm(form({ price: '-1' }))).toEqual({ price: '价格要填不小于 0 的数字' })
  })

  it('正式度超范围时提示', () => {
    expect(validateItemForm(form({ formality: '6' })).formality).toBeTruthy()
    expect(validateItemForm(form({ formality: '0' })).formality).toBeTruthy()
  })

  it('合法值不报错', () => {
    expect(validateItemForm(form({ price: '0', formality: '5' }))).toEqual({})
  })
})
