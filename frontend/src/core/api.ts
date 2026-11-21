import type {
  Category,
  ItemFilter,
  ItemList,
  Occasion,
  RecommendResult,
  SavedOutfit,
  Warmth,
  Weather,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...((init?.headers as Record<string, string> | undefined) ?? {}),
    },
  })
  if (!res.ok) {
    let detail = `请求失败（${res.status}）`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = '表单校验未通过'
      else if (body.detail && typeof body.detail === 'object' && 'message' in body.detail) {
        detail = String((body.detail as { message: unknown }).message)
      }
    } catch {
      /* 非 JSON 响应，保留默认文案 */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export function listItems(filter: ItemFilter = {}): Promise<ItemList> {
  const params = new URLSearchParams()
  for (const category of filter.category ?? []) params.append('category', category)
  if (filter.occasion) params.append('occasion', filter.occasion)
  if (filter.incomplete) params.set('incomplete', 'true')
  if (filter.q) params.append('q', filter.q)
  if (filter.limit != null) params.set('limit', String(filter.limit))
  if (filter.offset != null) params.set('offset', String(filter.offset))
  const query = params.toString()
  return request<ItemList>(`/items${query ? `?${query}` : ''}`)
}

export function createItem(payload: {
  category: Category
  warmth?: Warmth | null
  occasion?: Occasion | null
  name?: string
  image_ids?: number[]
}): Promise<import('./types').Item> {
  return request('/items', { method: 'POST', body: JSON.stringify(payload) })
}

export function deleteItem(id: number): Promise<void> {
  return request(`/items/${id}`, { method: 'DELETE' })
}

export function getRecommend(
  options: {
    city?: string
    occasion?: Occasion
    mode?: 'rules' | 'llm'
    /** BYOK：只放在请求头，不进 URL、不落日志 */
    llmKey?: string
  } = {},
): Promise<RecommendResult> {
  const query = new URLSearchParams()
  if (options.city) query.set('city', options.city)
  if (options.occasion) query.set('occasion', options.occasion)
  if (options.mode) query.set('mode', options.mode)
  const suffix = query.toString()

  const headers: Record<string, string> = {}
  if (options.mode === 'llm' && options.llmKey) headers['X-LLM-Key'] = options.llmKey

  return request<RecommendResult>(`/recommend${suffix ? `?${suffix}` : ''}`, { headers })
}

/** 只回传后端需要的快照字段，不要把整个 Weather 塞进去。 */
function weatherPayload(weather: Weather) {
  return {
    date: weather.date,
    t_min: weather.t_min,
    t_max: weather.t_max,
    feels_min: weather.feels_min,
    feels_max: weather.feels_max,
    precip_prob: weather.precip_prob,
    wind: weather.wind,
    uv: weather.uv,
    weather_code: weather.weather_code,
    weather_text: weather.weather_text,
  }
}

export function saveOutfit(payload: {
  item_ids: number[]
  weather: Weather | null
  note?: string
}): Promise<SavedOutfit> {
  return request('/outfits', {
    method: 'POST',
    body: JSON.stringify({
      item_ids: payload.item_ids,
      weather: payload.weather ? weatherPayload(payload.weather) : null,
      note: payload.note,
    }),
  })
}
