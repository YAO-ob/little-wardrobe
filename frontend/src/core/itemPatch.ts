/** 单品编辑表单 → PATCH body，以及表单校验。纯函数，便于单测。 */

import type { Category, Item } from './types'
import { visibleFields, type FieldKey } from './itemFields'

export interface ItemFormValues {
  category: Category
  warmth: string
  occasion: string[]
  color_family: string
  brand: string
  material: string
  formality: string
  layer: string
  season: string[]
  price: string
  note: string
  description: string
  size: string
  purchase_url: string
  care_text: string
  care_symbols: string[]
}

export type ItemFormErrors = Partial<Record<keyof ItemFormValues, string>>

const text = (value: string): string | null => {
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

const sameList = (left: string[], right: string[]): boolean => {
  if (left.length !== right.length) return false
  const a = [...left].sort()
  const b = [...right].sort()
  return a.every((value, index) => value === b[index])
}

export function validateItemForm(form: ItemFormValues): ItemFormErrors {
  const errors: ItemFormErrors = {}

  if (form.price.trim() !== '') {
    const price = Number(form.price)
    if (!Number.isFinite(price) || price < 0) {
      errors.price = '价格要填不小于 0 的数字'
    }
  }

  if (form.formality !== '') {
    const formality = Number(form.formality)
    if (!Number.isInteger(formality) || formality < 1 || formality > 5) {
      errors.formality = '正式度只能是 1–5'
    }
  }

  return errors
}

/**
 * 只把「改过」的字段放进 body：
 * 空字符串转 null（清空），没动的字段干脆不出现。
 */
export function buildItemPatch(form: ItemFormValues, initial: Item): Record<string, unknown> {
  const patch: Record<string, unknown> = {}

  // 品类不允许清空（数据库 NOT NULL），只有改了才进 patch
  if (form.category !== initial.category) {
    patch.category = form.category
  }

  const initialWarmth = initial.warmth == null ? '' : String(initial.warmth)
  if (form.warmth !== initialWarmth) {
    patch.warmth = form.warmth === '' ? null : Number(form.warmth)
  }

  if (!sameList(form.occasion, initial.occasion ?? [])) {
    patch.occasion = form.occasion.length > 0 ? form.occasion : null
  }

  const textFields: [keyof ItemFormValues, keyof Item][] = [
    ['color_family', 'color_family'],
    ['brand', 'brand'],
    ['material', 'material'],
    ['note', 'note'],
    ['description', 'description'],
    ['size', 'size'],
    ['purchase_url', 'purchase_url'],
    ['care_text', 'care_text'],
  ]
  for (const [formKey, itemKey] of textFields) {
    const current = String(form[formKey] ?? '')
    const before = String((initial[itemKey] as string | null | undefined) ?? '')
    if (current !== before) patch[itemKey] = text(current)
  }

  const initialFormality = initial.formality == null ? '' : String(initial.formality)
  if (form.formality !== initialFormality) {
    patch.formality = form.formality === '' ? null : Number(form.formality)
  }

  const initialLayer = initial.layer ?? ''
  if (form.layer !== initialLayer) {
    patch.layer = form.layer === '' ? null : form.layer
  }

  if (!sameList(form.season, initial.season ?? [])) {
    patch.season = form.season
  }

  if (!sameList(form.care_symbols, initial.care_symbols ?? [])) {
    patch.care_symbols = form.care_symbols
  }

  const initialPrice = initial.price == null ? '' : String(initial.price)
  if (form.price !== initialPrice) {
    patch.price = form.price.trim() === '' ? null : Number(form.price)
  }

  // 被品类隐藏的字段即便「看起来改过」也不提交——切一下品类不该把原值覆盖掉
  const visible = visibleFields(form.category)
  for (const key of Object.keys(patch)) {
    if (key === 'category') continue
    if (!visible.has(key as FieldKey)) delete patch[key]
  }

  return patch
}
