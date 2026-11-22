/** 购物截图识别结果 → 表单预填：只填空字段，绝不覆盖用户已输入的值。 */

export interface ReceiptFields {
  brand?: string | null
  price?: number | null
  material?: string | null
  color_family?: string | null
  size?: string | null
}

export const RECEIPT_KEYS = ['brand', 'price', 'material', 'color_family', 'size'] as const
export type ReceiptKey = (typeof RECEIPT_KEYS)[number]

export interface ReceiptForm {
  brand: string
  price: string
  material: string
  color_family: string
  size: string
}

/** 返回合并后的表单 + 实际被填充的字段（用于打「识别」标记）。 */
export function mergeReceipt(
  form: ReceiptForm,
  receipt: ReceiptFields,
): { form: ReceiptForm; filled: ReceiptKey[] } {
  const next: ReceiptForm = { ...form }
  const filled: ReceiptKey[] = []

  for (const key of RECEIPT_KEYS) {
    const current = next[key].trim()
    if (current !== '') continue // 用户已经填了，不覆盖

    const value = receipt[key]
    if (value === null || value === undefined) continue
    const text = typeof value === 'number' ? String(value) : value.trim()
    if (text === '') continue

    next[key] = text
    filled.push(key)
  }

  return { form: next, filled }
}
