import { CATEGORIES } from '../../core/labels'
import type { Category } from '../../core/types'

const CATEGORY_ICON: Record<string, string> = Object.fromEntries(
  CATEGORIES.map((c) => [c.value, c.icon]),
)

/** 颜色族 → 圆点色值（与 labels 里的 14 族对齐，tailwind 动态类不安全所以用内联色）。 */
const COLOR_HEX: Record<string, string> = {
  black: '#1f2937',
  white: '#f5f5f0',
  gray: '#9ca3af',
  beige: '#d4c4a0',
  brown: '#92400e',
  blue: '#3b82f6',
  navy: '#1e3a8a',
  green: '#22c55e',
  red: '#ef4444',
  pink: '#ec4899',
  purple: '#a855f7',
  yellow: '#eab308',
  orange: '#f97316',
  multi: '#a78bfa',
}

/** 无图单品的占位块：品类图标居中，右上角一个颜色小圆点。 */
export default function ItemPlaceholder({
  category,
  colorFamily,
  className = '',
}: {
  category: Category
  colorFamily?: string | null
  className?: string
}) {
  const hex = colorFamily ? COLOR_HEX[colorFamily] : undefined
  return (
    <div
      className={`flex aspect-square w-full items-center justify-center bg-black/5 ${className}`}
    >
      <span className="relative text-2xl">
        {CATEGORY_ICON[category] ?? '🧺'}
        {hex && (
          <span
            className="absolute -right-1.5 -top-1 h-2.5 w-2.5 rounded-full border border-white shadow-sm"
            style={{ backgroundColor: hex }}
            aria-hidden
          />
        )}
      </span>
    </div>
  )
}
