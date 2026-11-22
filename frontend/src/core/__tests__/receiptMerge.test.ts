// @vitest-environment jsdom
/** 截图识别预填：只填空字段，不覆盖用户输入。 */

import { describe, expect, it } from 'vitest'
import { mergeReceipt, type ReceiptForm } from '../receiptMerge'

const empty: ReceiptForm = {
  brand: '',
  price: '',
  material: '',
  color_family: '',
  size: '',
}

const receipt = {
  brand: '优衣库',
  price: 199,
  material: '棉',
  color_family: '藏青',
  size: 'M',
}

describe('mergeReceipt', () => {
  it('空表单全填上，并返回被填充的字段', () => {
    const { form, filled } = mergeReceipt(empty, receipt)

    expect(form).toEqual({
      brand: '优衣库',
      price: '199',
      material: '棉',
      color_family: '藏青',
      size: 'M',
    })
    expect(filled).toEqual(['brand', 'price', 'material', 'color_family', 'size'])
  })

  it('用户已填的字段不被覆盖', () => {
    const typed = { ...empty, brand: '我自己填的' }

    const { form, filled } = mergeReceipt(typed, receipt)

    expect(form.brand).toBe('我自己填的')
    expect(filled).toEqual(['price', 'material', 'color_family', 'size'])
  })

  it('识别结果为空时不改动表单', () => {
    const { form, filled } = mergeReceipt(empty, { brand: null, price: null })

    expect(form).toEqual(empty)
    expect(filled).toEqual([])
  })
})
