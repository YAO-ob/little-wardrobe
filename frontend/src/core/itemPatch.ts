/** 单品编辑表单 → PATCH body，以及表单校验。纯函数，便于单测。 */

import type { Item } from './types'

export interface ItemFormValues {
  color_family: string
  brand: string
  material: string
  formality: string
  layer: string
  season: string[]
  price: string
  note: string
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

  const textFields: [keyof ItemFormValues, keyof Item][] = [
    ['color_family', 'color_family'],
    ['brand', 'brand'],
    ['material', 'material'],
    ['note', 'note'],
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

  const initialPrice = initial.price == null ? '' : String(initial.price)
  if (form.price !== initialPrice) {
    patch.price = form.price.trim() === '' ? null : Number(form.price)
  }

  return patch
}
