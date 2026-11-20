/**
 * 录入页的键盘映射与焦点守卫。
 *
 * 从 CapturePage 里抽出来，一是为了能单独测（R2 的 bug 就出在守卫的判断条件上），
 * 二是以后加别的快捷键时改一处就够。
 */

import type { Category, Warmth } from './types'
import { CATEGORIES, WARMTHS } from './labels'

export type ShortcutAction =
  | { type: 'category'; value: Category }
  | { type: 'warmth'; value: Warmth }
  | { type: 'save' }
  | { type: 'skip' }

/** 会把字符键吃掉的「文本类」输入；file/button/checkbox 等一律不该拦。 */
const TEXT_INPUT_TYPES = new Set([
  'text',
  'search',
  'number',
  'password',
  'email',
  'tel',
  'url',
  'date',
  'datetime-local',
  'month',
  'week',
  'time',
])

/**
 * 判断当前焦点元素是不是「正在输入文字」。
 * 是的话键盘快捷键必须让路，否则用户在搜索框里打 1 会被当成选品类。
 */
export function isTextEntry(target: EventTarget | null): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== 'string') return false
  const element = target as HTMLElement
  // jsdom 不实现 isContentEditable，所以属性兜底
  const editable =
    element.isContentEditable ||
    element.getAttribute?.('contenteditable') === 'true' ||
    element.getAttribute?.('contenteditable') === ''
  if (editable) return true
  if (element.tagName === 'TEXTAREA' || element.tagName === 'SELECT') return true
  if (element.tagName === 'INPUT') {
    const type = (element as HTMLInputElement).type ?? 'text'
    return TEXT_INPUT_TYPES.has(String(type).toLowerCase())
  }
  return false
}

/** 按键 → 动作。不认识的键返回 null，交给浏览器。 */
export function resolveShortcut(key: string): ShortcutAction | null {
  const category = CATEGORIES.find((item) => item.key === key)
  if (category) return { type: 'category', value: category.value }

  const lowered = key.toLowerCase()
  const warmth = WARMTHS.find((item) => item.key === lowered)
  if (warmth) return { type: 'warmth', value: warmth.value }

  if (key === 'Enter') return { type: 'save' }
  if (key === 'Backspace') return { type: 'skip' }

  return null
}
