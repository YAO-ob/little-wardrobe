/** 纯文字录入的纯逻辑：截断、描述首行、以及 UI 表单 → 提交 DTO 的白名单组装。
 *
 * 这里刻意把「用于渲染/交互的状态」和「提交给后端的 payload」分开：
 * UI 表单可以带 categorySource 之类的派生字段，但 buildTextItemPayload 只挑契约字段，
 * 杜绝派生字段泄漏进请求体。
 */

import type { Category, Occasion, Warmth } from './types'

export const MAX_DESCRIPTION = 300

/** 超长截断，不让吞 token 或触发 422。 */
export function truncateText(text: string, max: number = MAX_DESCRIPTION): string {
  return text.slice(0, max)
}

/** 取描述的第一行（去首尾空白），空则 ''。卡片/列表展示用——多行描述只露一行。 */
export function firstLine(text: string | null | undefined): string {
  return text?.split('\n')[0]?.trim() ?? ''
}

/** 卡片首行：优先描述第一行，描述为空/纯空白时回退到传入的兜底（如「上衣 · 米白」）。 */
export function cardHeadline(description: string | null | undefined, fallback: string): string {
  return firstLine(description) || fallback
}

/** 文字录入的 UI 表单状态（渲染/交互用）。 */
export interface TextEntryForm {
  description: string
  category: Category | null
  warmth: Warmth | null
  occasion: Occasion[]
  color_family: string | null
  material: string | null
}

/** 从 UI 表单白名单组装 createItem 的 DTO。category 由调用方保证非空。 */
export function buildTextItemPayload(form: TextEntryForm) {
  const description = truncateText(form.description.trim()) || undefined
  return {
    category: form.category as Category,
    warmth: form.warmth ?? undefined,
    occasion: form.occasion.length ? form.occasion : undefined,
    color_family: form.color_family ?? undefined,
    material: form.material ?? undefined,
    description,
  }
}
