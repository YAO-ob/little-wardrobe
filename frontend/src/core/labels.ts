import type { Category, Occasion, Warmth } from './types'

export const CATEGORIES: { value: Category; label: string; icon: string; key: string }[] = [
  { value: 'top', label: '上衣', icon: '👕', key: '1' },
  { value: 'outer', label: '外套', icon: '🧥', key: '2' },
  { value: 'bottom', label: '下装', icon: '👖', key: '3' },
  { value: 'shoes', label: '鞋', icon: '👟', key: '4' },
  { value: 'accessory', label: '配饰', icon: '🧢', key: '5' },
  { value: 'dress', label: '连衣裙', icon: '👗', key: '6' },
]

export const WARMTHS: { value: Warmth; label: string; key: string }[] = [
  { value: 1, label: '薄', key: 'q' },
  { value: 2, label: '中', key: 'w' },
  { value: 3, label: '厚', key: 'e' },
]

export const OCCASIONS: { value: Occasion; label: string }[] = [
  { value: 'casual', label: '日常' },
  { value: 'work', label: '通勤' },
  { value: 'sport', label: '运动' },
  { value: 'formal', label: '正式' },
]

export const CATEGORY_LABEL: Record<Category, string> = Object.fromEntries(
  CATEGORIES.map((c) => [c.value, c.label]),
) as Record<Category, string>

export const WARMTH_LABEL: Record<number, string> = { 1: '薄', 2: '中', 3: '厚' }

export const OCCASION_LABEL: Record<string, string> = Object.fromEntries(
  OCCASIONS.map((o) => [o.value, o.label]),
)

/** 颜色家族：库里只存英文枚举，中文只做显示（与后端 COLOR_FAMILIES 一致）。 */
export const COLOR_LABELS: Record<string, string> = {
  black: '黑',
  white: '白',
  gray: '灰',
  beige: '米',
  brown: '棕',
  blue: '蓝',
  navy: '藏青',
  green: '绿',
  red: '红',
  pink: '粉',
  purple: '紫',
  yellow: '黄',
  orange: '橙',
  multi: '花色',
}

export const COLOR_OPTIONS: { value: string; label: string }[] = Object.entries(
  COLOR_LABELS,
).map(([value, label]) => ({ value, label }))

/** 洗护符号：前后端共用这 12 个编码，不许自由文本（否则「30度/30℃/温水」会并存）。 */
export const CARE_SYMBOLS: { value: string; label: string }[] = [
  { value: 'wash_30', label: '30℃机洗' },
  { value: 'wash_40', label: '40℃机洗' },
  { value: 'hand_wash', label: '手洗' },
  { value: 'no_wash', label: '不可水洗' },
  { value: 'bleach_ok', label: '可漂白' },
  { value: 'no_bleach', label: '不可漂白' },
  { value: 'tumble_low', label: '低温烘干' },
  { value: 'no_tumble', label: '不可烘干' },
  { value: 'iron_low', label: '低温熨烫' },
  { value: 'no_iron', label: '不可熨烫' },
  { value: 'dry_clean', label: '干洗' },
  { value: 'no_dry_clean', label: '不可干洗' },
]

export const CARE_SYMBOL_LABEL: Record<string, string> = Object.fromEntries(
  CARE_SYMBOLS.map((s) => [s.value, s.label]),
)

/** 互斥组：同组最多选一个（后端也会校验，前端先置灰）。 */
export const CARE_EXCLUSIVE_GROUPS: string[][] = [
  ['wash_30', 'wash_40', 'hand_wash', 'no_wash'],
  ['bleach_ok', 'no_bleach'],
  ['tumble_low', 'no_tumble'],
  ['iron_low', 'no_iron'],
  ['dry_clean', 'no_dry_clean'],
]
