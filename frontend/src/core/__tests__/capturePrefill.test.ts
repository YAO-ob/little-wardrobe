// @vitest-environment jsdom
/** 建议合并：用户选择优先，没选才填。 */

import { describe, expect, it } from 'vitest'
import { chooseCategory, mergeSuggestion, type Prefillable } from '../capturePrefill'

const empty: Prefillable = {
  category: null,
  warmth: null,
  categorySource: null,
  warmthSource: null,
}

describe('mergeSuggestion', () => {
  it('用户已经选过的字段不被建议覆盖', () => {
    const chosen = chooseCategory(empty, 'top')
    const merged = mergeSuggestion(chosen, { category: 'shoes', warmth: 2 })

    expect(merged.category).toBe('top')
    expect(merged.categorySource).toBe('user')
    expect(merged.warmth).toBe(2)
    expect(merged.warmthSource).toBe('suggestion')
  })

  it('没选过的字段填入建议并标记来源', () => {
    const merged = mergeSuggestion(empty, { category: 'shoes', warmth: 2 })

    expect(merged.category).toBe('shoes')
    expect(merged.categorySource).toBe('suggestion')
    expect(merged.warmth).toBe(2)
    expect(merged.warmthSource).toBe('suggestion')
  })

  it('建议为空时草稿不变', () => {
    expect(mergeSuggestion(empty, null)).toEqual(empty)
    expect(mergeSuggestion(empty, { category: null, warmth: null })).toEqual(empty)
  })
})
