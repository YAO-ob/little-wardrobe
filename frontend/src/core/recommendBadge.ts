/** 搭配来源徽标与降级原因文案：纯逻辑，方便单测。 */

export interface RecommendMeta {
  source: string
  cached: boolean
  fallback_reason: string | null
}

const FALLBACK_TEXT: Record<string, string> = {
  no_key: '没有配置 API key',
  rate_limited: '请求太频繁，稍后再试',
  timeout: '模型响应超时',
  invalid_ids: '模型给的单品不在候选里',
  invalid_outfit: '模型给的搭配不完整',
  truncated: '模型输出被截断',
  missing_category: '衣橱里缺基础品类',
  bad_json: '模型返回的内容看不懂',
  bad_structure: '模型返回的结构不对',
  network: '连不上模型服务',
  empty_pool: '候选单品不够',
  empty_wardrobe: '衣橱是空的',
}

export function fallbackText(reason: string | null | undefined): string | null {
  if (!reason) return null
  return FALLBACK_TEXT[reason] ?? '模型暂时不可用'
}

export interface BadgeInfo {
  label: string
  /** ai = 模型精选；cache = 命中缓存；rules = 规则推荐（含降级） */
  tone: 'ai' | 'cache' | 'rules'
  detail: string | null
}

export function badgeFor(meta: RecommendMeta): BadgeInfo {
  if (meta.source === 'llm') {
    return meta.cached
      ? { label: 'AI 精选 · 缓存', tone: 'cache', detail: null }
      : { label: 'AI 精选', tone: 'ai', detail: null }
  }
  return { label: '规则推荐', tone: 'rules', detail: fallbackText(meta.fallback_reason) }
}

/** 已保存时回显用：sk-****；太长也不泄露。 */
export function maskKey(key: string): string {
  const trimmed = key.trim()
  if (!trimmed) return ''
  if (trimmed.length <= 6) return '****'
  return `${trimmed.slice(0, 3)}****`
}
