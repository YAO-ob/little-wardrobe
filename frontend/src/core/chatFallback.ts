/** 降级原因 → 一句人话。没有原因就什么都不显示（不加噪音）。 */

export const FALLBACK_HINTS: Record<string, string> = {
  no_key: '没配置 API key，用的是规则推荐',
  rate_limited: '请求太频繁，暂时用规则推荐',
  invalid_ids: '模型这次没挑对，用了规则推荐',
  invalid_outfit: '模型这次没挑对，用了规则推荐',
  invalid_intent: '模型没理解对，用了规则推荐',
  timeout: '模型超时，用了规则推荐',
  network: '模型超时，用了规则推荐',
  weather_unavailable: '这个地点取不到天气',
}

export function fallbackHint(reason?: string | null): string | null {
  if (!reason) return null
  return FALLBACK_HINTS[reason] ?? null
}
