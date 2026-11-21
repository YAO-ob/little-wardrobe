import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteItem, listItems } from '../../core/api'
import { resolveDeleteClick } from '../../core/deleteConfirm'
import { CATEGORIES, CATEGORY_LABEL, OCCASIONS, OCCASION_LABEL, WARMTH_LABEL } from '../../core/labels'
import type { Category, Item, Occasion } from '../../core/types'
import { toast } from '../../adapters/toast'
import ItemDetailModal from '../components/ItemDetailModal'

export default function GalleryPage() {
  const queryClient = useQueryClient()
  const [categories, setCategories] = useState<Category[]>([])
  const [occasion, setOccasion] = useState<Occasion | null>(null)
  const [incompleteOnly, setIncompleteOnly] = useState(false)
  const [q, setQ] = useState('')
  const [deletingId, setDeletingId] = useState<number | null>(null)
  // 处于「确认删除」状态的卡片；null 表示没有
  const [confirmingId, setConfirmingId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Item | null>(null)

  const filter = useMemo(
    () => ({ category: categories, occasion: occasion ?? undefined, incomplete: incompleteOnly, q }),
    [categories, occasion, incompleteOnly, q],
  )

  const { data, isLoading, error } = useQuery({
    queryKey: ['items', filter],
    queryFn: () => listItems({ ...filter, limit: 200 }),
  })

  function toggleCategory(value: Category) {
    setCategories((prev) =>
      prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value],
    )
  }

  // 软删除：只打 deleted_at，media 文件与 images.item_id 都不动
  async function remove(item: Item) {
    setDeletingId(item.id)
    try {
      await deleteItem(item.id)
      await queryClient.invalidateQueries({ queryKey: ['items'] })
      if (detail?.id === item.id) setDetail(null)
      toast('已删除')
    } catch (err) {
      toast(err instanceof Error ? err.message : '删除失败')
    } finally {
      setDeletingId(null)
      setConfirmingId(null)
    }
  }

  function onDeleteClick(item: Item) {
    const action = resolveDeleteClick(confirmingId, item.id)
    if (action.type === 'arm') setConfirmingId(action.id)
    else void remove(item)
  }

  // 换筛选 / 改搜索词就把待确认状态收回，避免「确认」跨上下文残留
  useEffect(() => {
    setConfirmingId(null)
  }, [filter])

  const items = data?.items ?? []

  return (
    <div
      className="space-y-3"
      onClick={(event) => {
        // 点在别处（不是任何删除按钮）就收回待确认状态
        const target = event.target as HTMLElement | null
        if (confirmingId !== null && !target?.closest('.card-delete')) setConfirmingId(null)
      }}
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="搜名字 / 备注"
        className="w-full rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-black/30"
      />

      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {CATEGORIES.map((c) => (
          <button
            key={c.value}
            type="button"
            onClick={() => toggleCategory(c.value)}
            className={`shrink-0 rounded-full border px-3 py-1 text-xs transition ${
              categories.includes(c.value)
                ? 'border-black bg-black text-white'
                : 'border-black/10 bg-white text-black/60'
            }`}
          >
            {c.label}
          </button>
        ))}
        <span className="w-px shrink-0 self-stretch bg-black/10" />
        {OCCASIONS.map((o) => (
          <button
            key={o.value}
            type="button"
            onClick={() => setOccasion(occasion === o.value ? null : o.value)}
            className={`shrink-0 rounded-full border px-3 py-1 text-xs transition ${
              occasion === o.value
                ? 'border-black bg-black text-white'
                : 'border-black/10 bg-white text-black/60'
            }`}
          >
            {o.label}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setIncompleteOnly((v) => !v)}
          className={`shrink-0 rounded-full border px-3 py-1 text-xs transition ${
            incompleteOnly
              ? 'border-amber-500 bg-amber-500 text-white'
              : 'border-black/10 bg-white text-black/60'
          }`}
        >
          信息不全
        </button>
      </div>

      {isLoading && <p className="py-10 text-center text-sm text-black/40">加载中…</p>}
      {error && <p className="py-10 text-center text-sm text-red-500">加载失败</p>}

      {!isLoading && !error && items.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-16 text-black/40">
          <span className="text-3xl">🧺</span>
          <p className="text-sm">
            {categories.length || occasion || incompleteOnly || q
              ? '这个筛选下没有衣服'
              : '还没有衣服，去「录入」加一件'}
          </p>
        </div>
      )}

      {items.length > 0 && (
        <>
          <p className="text-xs text-black/40">
            共 {data?.total ?? items.length} 件
            {(categories.length > 0 || occasion || incompleteOnly || q) && ' · 已筛选'}
          </p>
          <div className="grid grid-cols-3 gap-2">
            {items.map((item) => {
              const incomplete = !item.color_family
              return (
                <figure
                  key={item.id}
                  onClick={() => setDetail(item)}
                  className="group relative cursor-pointer overflow-hidden rounded-xl bg-white shadow-sm"
                >
                  {item.image ? (
                    <img
                      src={item.image.thumb_url}
                      alt={item.name}
                      loading="lazy"
                      className="aspect-square w-full object-cover"
                    />
                  ) : (
                    <div className="flex aspect-square w-full items-center justify-center bg-black/5 text-2xl">
                      🧺
                    </div>
                  )}
                  {incomplete && (
                    <span className="absolute left-1 top-1 rounded-full bg-amber-500/90 px-1.5 py-0.5 text-[10px] text-white">
                      信息不全
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(event) => {
                      // 点删除不能顺带打开详情
                      event.stopPropagation()
                      onDeleteClick(item)
                    }}
                    disabled={deletingId === item.id}
                    data-armed={confirmingId === item.id}
                    aria-label={
                      confirmingId === item.id ? `确认删除${item.name}` : `删除${item.name}`
                    }
                    className={`card-delete pointer-events-auto absolute right-1 top-1 z-10 flex min-h-7 min-w-12 items-center justify-center rounded-full p-1.5 text-[10px] leading-none text-white transition-colors after:absolute after:-inset-1.5 after:content-[''] disabled:opacity-40 ${
                      confirmingId === item.id ? 'bg-red-600' : 'bg-black/65'
                    }`}
                  >
                    {deletingId === item.id
                      ? '删除中'
                      : confirmingId === item.id
                        ? '确认删除'
                        : '删除'}
                  </button>
                  <figcaption className="space-y-0.5 px-2 py-1.5">
                    <p className="truncate text-xs font-medium">
                      {CATEGORY_LABEL[item.category] ?? item.category}
                      {item.warmth ? ` · ${WARMTH_LABEL[item.warmth]}` : ''}
                    </p>
                    <p className="truncate text-[11px] text-black/40">
                      {item.occasion ? OCCASION_LABEL[item.occasion] : '未填场合'}
                    </p>
                  </figcaption>
                </figure>
              )
            })}
          </div>
        </>
      )}

      {detail && <ItemDetailModal item={detail} onClose={() => setDetail(null)} />}
    </div>
  )
}
