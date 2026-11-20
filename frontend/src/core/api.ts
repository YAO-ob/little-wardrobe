import type { Category, ItemFilter, ItemList, Occasion, Warmth } from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = `请求失败（${res.status}）`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = '表单校验未通过'
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
