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
