/**
 * 城市列表的兜底。
 * 真正的来源是后端 GET /api/cities；这里只在接口失败时用，
 * 保证下拉仍然可用（不会因为拿不到列表就白屏）。
 */

export const FALLBACK_CITIES = [
  '杭州',
  '上海',
  '北京',
  '广州',
  '深圳',
  '成都',
  '南京',
  '武汉',
] as const

export const DEFAULT_CITY = '杭州'

/** 只接受给定列表里的城市；空值或表外值一律回落默认城市。 */
export function resolveCity(raw: string | null | undefined, available: readonly string[]): string {
  if (!raw) return DEFAULT_CITY
  return available.includes(raw) ? raw : DEFAULT_CITY
}
