/** 天气快照的「多久以前」文案：纯函数，便于单测。 */

export function weatherAgeText(
  fetchedAt: string | null | undefined,
  now: number = Date.now(),
): string {
  if (!fetchedAt) return '较早的缓存'
  const timestamp = Date.parse(fetchedAt)
  if (Number.isNaN(timestamp)) return '较早的缓存'

  const hours = (now - timestamp) / 3_600_000
  if (hours < 1) return '不到 1 小时前'
  return `${Math.round(hours)} 小时前`
}
