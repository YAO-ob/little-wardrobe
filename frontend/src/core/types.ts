export type Category = 'top' | 'outer' | 'bottom' | 'shoes' | 'accessory' | 'dress'
export type Occasion = 'casual' | 'work' | 'sport' | 'formal'
export type Warmth = 1 | 2 | 3
export type Layer = 'inner' | 'mid' | 'outer'

export interface ItemImage {
  id: number
  url: string
  thumb_url: string
  width?: number | null
  height?: number | null
}

export interface Item {
  id: number
  name: string
  category: Category
  subcategory?: string | null
  color_family?: string | null
  color_hex?: string | null
  season: string[]
  occasion?: Occasion | null
  warmth?: Warmth | null
  formality?: number | null
  layer?: Layer | null
  material?: string | null
  brand?: string | null
  price?: number | null
  purchased_at?: string | null
  note?: string | null
  created_at?: string | null
  images: ItemImage[]
  image?: ItemImage | null
}

export interface ItemList {
  total: number
  items: Item[]
}

export interface NewItem {
  name?: string
  category: Category
  subcategory?: string | null
  color_family?: string | null
  color_hex?: string | null
  season?: string[]
  occasion?: Occasion | null
  warmth?: Warmth | null
  formality?: number | null
  layer?: Layer | null
  material?: string | null
  brand?: string | null
  price?: number | null
  purchased_at?: string | null
  note?: string | null
  image_ids?: number[]
}

export interface ItemFilter {
  category?: Category[]
  occasion?: Occasion
  incomplete?: boolean
  q?: string
  limit?: number
  offset?: number
}
