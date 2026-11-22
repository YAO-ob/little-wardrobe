/** 自动识别的建议值如何合并进草稿。纯函数，便于单测。 */

import type { Category, Warmth } from './types'

export interface Suggestion {
  category: Category | null
  warmth: Warmth | null
}

export type FieldSource = 'user' | 'suggestion'

export interface Prefillable {
  category: Category | null
  warmth: Warmth | null
  categorySource: FieldSource | null
  warmthSource: FieldSource | null
}

/**
 * 合并建议：用户手动选过的字段一律不覆盖（用户选择优先），
 * 没选过才填入，并标上 source='suggestion' 供 UI 显示虚框。
 */
export function mergeSuggestion<T extends Prefillable>(draft: T, suggestion: Suggestion | null): T {
  if (!suggestion) return draft

  const next = { ...draft }
  if (next.category === null && suggestion.category) {
    next.category = suggestion.category
    next.categorySource = 'suggestion'
  }
  if (next.warmth === null && suggestion.warmth) {
    next.warmth = suggestion.warmth
    next.warmthSource = 'suggestion'
  }
  return next
}

/** 用户点了品类：值改成用户选的，来源标记为 user。 */
export function chooseCategory<T extends Prefillable>(draft: T, category: Category): T {
  return { ...draft, category, categorySource: 'user' }
}

/** 用户点了厚薄：值改成用户选的，来源标记为 user。 */
export function chooseWarmth<T extends Prefillable>(draft: T, warmth: Warmth): T {
  return { ...draft, warmth, warmthSource: 'user' }
}
