/** 按品类决定详情弹层显示哪些字段。纯函数，可测。 */

import type { Category } from './types'

export type FieldKey =
  | 'category'
  | 'warmth'
  | 'occasion'
  | 'formality'
  | 'color_family'
  | 'brand'
  | 'price'
  | 'purchase_url'
  | 'note'
  | 'material'
  | 'care_text'
  | 'layer'
  | 'season'
  | 'size'
  | 'care_symbols'

/** 任何品类都显示的字段。 */
const ALWAYS: FieldKey[] = [
  'category',
  'occasion',
  'formality',
  'color_family',
  'brand',
  'price',
  'purchase_url',
  'note',
  'material',
  'care_text',
]

// 配饰没有厚薄/季节/尺码的概念；鞋和配饰没有洗护符号（这类通常直接擦或干洗店处理）
const WITH_WARMTH: Category[] = ['top', 'outer', 'bottom', 'shoes', 'dress']
const WITH_LAYER: Category[] = ['top', 'outer']
const WITH_SEASON: Category[] = ['top', 'outer', 'bottom', 'shoes', 'dress']
const WITH_SIZE: Category[] = ['top', 'outer', 'bottom', 'shoes', 'dress']
const WITH_CARE_SYMBOLS: Category[] = ['top', 'outer', 'bottom', 'dress']

export function visibleFields(category: Category): Set<FieldKey> {
  const fields = new Set<FieldKey>(ALWAYS)
  if (WITH_WARMTH.includes(category)) fields.add('warmth')
  if (WITH_LAYER.includes(category)) fields.add('layer')
  if (WITH_SEASON.includes(category)) fields.add('season')
  if (WITH_SIZE.includes(category)) fields.add('size')
  if (WITH_CARE_SYMBOLS.includes(category)) fields.add('care_symbols')
  return fields
}
