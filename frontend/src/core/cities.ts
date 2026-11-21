/** 内置城市列表：与后端 backend/app/data/cities.py 保持一致。 */

export const CITIES = ['杭州', '上海', '北京', '广州', '深圳', '成都', '南京', '武汉'] as const

export type CityName = (typeof CITIES)[number]

export const DEFAULT_CITY: CityName = '杭州'

/** 只接受内置城市；空值或表外值一律回落默认城市（后端对表外城市会 400）。 */
export function resolveCity(raw: string | null | undefined): CityName {
  if (!raw) return DEFAULT_CITY
  return (CITIES as readonly string[]).includes(raw) ? (raw as CityName) : DEFAULT_CITY
}
