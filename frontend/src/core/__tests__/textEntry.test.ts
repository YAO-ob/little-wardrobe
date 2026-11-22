/** W20：纯文字录入的纯逻辑——截断、描述首行、UI 表单 → 提交 DTO 的白名单。 */

import { describe, expect, it } from 'vitest'
import {
  buildTextItemPayload,
  cardHeadline,
  firstLine,
  MAX_DESCRIPTION,
  truncateText,
  type TextEntryForm,
} from '../textEntry'

const baseForm: TextEntryForm = {
  description: '米白色亚麻长袖衬衫',
  category: 'top',
  warmth: 1,
  occasion: ['work'],
  color_family: 'beige',
  material: '亚麻',
}

describe('firstLine', () => {
  it('取第一行并去掉首尾空白', () => {
    expect(firstLine('  米白衬衫  \n第二行')).toBe('米白衬衫')
  })

  it('空值或只有空行返回空串', () => {
    expect(firstLine('')).toBe('')
    expect(firstLine(null)).toBe('')
    expect(firstLine(undefined)).toBe('')
    expect(firstLine('\n\n')).toBe('')
  })
})

describe('truncateText', () => {
  it('超过上限截断', () => {
    expect(truncateText('字'.repeat(400)).length).toBe(MAX_DESCRIPTION)
  })

  it('不超过原样返回', () => {
    expect(truncateText('短')).toBe('短')
  })
})

describe('buildTextItemPayload', () => {
  it('完整表单包含所有契约字段', () => {
    expect(buildTextItemPayload(baseForm)).toEqual({
      category: 'top',
      warmth: 1,
      occasion: ['work'],
      color_family: 'beige',
      material: '亚麻',
      description: '米白色亚麻长袖衬衫',
    })
  })

  it('空值字段不进 payload（undefined），空描述也不带', () => {
    const p = buildTextItemPayload({
      ...baseForm,
      warmth: null,
      occasion: [],
      color_family: null,
      material: null,
      description: '   ',
    })
    expect(p.warmth).toBeUndefined()
    expect(p.occasion).toBeUndefined()
    expect(p.color_family).toBeUndefined()
    expect(p.material).toBeUndefined()
    expect(p.description).toBeUndefined()
  })

  it('description 超长截断到 300', () => {
    const p = buildTextItemPayload({ ...baseForm, description: '字'.repeat(400) })
    expect(p.description).toBe('字'.repeat(300))
  })

  it('不泄漏 UI 派生字段（categorySource / textValue 等不进请求体）', () => {
    const p = buildTextItemPayload(baseForm)
    expect(Object.keys(p)).not.toContain('categorySource')
    expect(Object.keys(p)).not.toContain('textValue')
  })
})

describe('cardHeadline（卡片首行回退）', () => {
  it('有描述取第一行', () => {
    expect(cardHeadline('米白衬衫\n第二行', '上衣 · 米白')).toBe('米白衬衫')
  })

  it('描述为空 / null / 纯空白时回退到兜底', () => {
    expect(cardHeadline('', '上衣 · 米白')).toBe('上衣 · 米白')
    expect(cardHeadline(null, '上衣 · 米白')).toBe('上衣 · 米白')
    expect(cardHeadline(undefined, '上衣 · 米白')).toBe('上衣 · 米白')
    expect(cardHeadline('   \n  ', '上衣 · 米白')).toBe('上衣 · 米白')
  })
})
