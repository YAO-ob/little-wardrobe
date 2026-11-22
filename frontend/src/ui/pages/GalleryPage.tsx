import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteItem, listItems } from '../../core/api'
import { isIncomplete } from '../../core/itemFields'
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
  const [filterOpen, setFilterOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  // 处于「确认删除」状态的卡片；null 表示没有
  const [confirmingId, setConfirmingId] = useState<number | null>(null)
  const [detail, setDetail] = useState<Item | null>(null)

  const filter = useMemo(
    () => ({ category: categories, occasion: occasion ?? undefined, incomplete: incompleteOnly, q }),
    [categories, occasion, incompleteOnly, q],
  )

  // 面板外筛选按钮上的角标：搜索词单独显示在输入框里，不计入
  const activeCount = categories.length + (occasion ? 1 : 0) + (incompleteOnly ? 1 : 0)

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
      <div className="flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜名字 / 备注"
          className="min-w-0 flex-1 rounded-xl border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-black/30"
        />
        <button
          type="button"
          onClick={() => setFilterOpen(true)}
          aria-label="筛选"
          className={`relative shrink-0 rounded-xl border px-3 py-2 text-sm transition ${
            activeCount > 0
              ? 'border-black bg-black text-white'
              : 'border-black/10 bg-white text-black/60'
          }`}
        >
          筛选
          {activeCount > 0 && (
            <span className="ml-1.5 inline-flex min-w-[18px] items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-medium leading-[18px] text-white">
              {activeCount}
            </span>
          )}
        </button>
      </div>

      {filterOpen && (
        <div
          className="overlay-enter fixed inset-0 z-40 flex items-end justify-center bg-black/50"
          onClick={() => setFilterOpen(false)}
        >
          <div
            className="sheet-enter max-h-[80vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-4"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <p className="text-sm font-medium">筛选</p>
              <button
                type="button"
                onClick={() => setFilterOpen(false)}
                className="text-xs text-black/40"
              >
                关闭
              </button>
            </div>

            <section className="mb-4">
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-[11px] text-black/50">种类</p>
                {categories.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setCategories([])}
                    className="text-[11px] text-black/40"
                  >
                    清除
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {CATEGORIES.map((c) => (
                  <button
                    key={c.value}
                    type="button"
                    onClick={() => toggleCategory(c.value)}
                    aria-pressed={categories.includes(c.value)}
                    className={`rounded-full border px-3 py-1 text-xs transition ${
                      categories.includes(c.value)
                        ? 'border-black bg-black text-white'
                        : 'border-black/10 bg-white text-black/60'
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            </section>

            <section className="mb-4">
              <p className="mb-1.5 text-[11px] text-black/50">场景</p>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => setOccasion(null)}
                  aria-pressed={occasion === null}
                  className={`rounded-full border px-3 py-1 text-xs transition ${
                    occasion === null
                      ? 'border-black bg-black text-white'
                      : 'border-black/10 bg-white text-black/60'
                  }`}
                >
                  全部
                </button>
                {OCCASIONS.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setOccasion(o.value)}
                    aria-pressed={occasion === o.value}
                    className={`rounded-full border px-3 py-1 text-xs transition ${
                      occasion === o.value
                        ? 'border-black bg-black text-white'
                        : 'border-black/10 bg-white text-black/60'
                    }`}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </section>

            <section className="mb-4">
              <p className="mb-1.5 text-[11px] text-black/50">其他</p>
              <button
                type="button"
                onClick={() => setIncompleteOnly((v) => !v)}
                aria-pressed={incompleteOnly}
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  incompleteOnly
                    ? 'border-amber-500 bg-amber-500 text-white'
                    : 'border-black/10 bg-white text-black/60'
                }`}
              >
                信息不全
              </button>
            </section>

            <div className="mt-5 flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setCategories([])
                  setOccasion(null)
                  setIncompleteOnly(false)
                  setFilterOpen(false)
                }}
                className="flex-1 rounded-xl border border-black/10 py-2.5 text-sm text-black/60"
              >
                重置
              </button>
              <button
                type="button"
                onClick={() => setFilterOpen(false)}
                className="flex-1 rounded-xl bg-black py-2.5 text-sm text-white"
              >
                完成
              </button>
            </div>
          </div>
        </div>
      )}

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
              const incomplete = isIncomplete(item)
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
                  {incomplete &&
                    (incompleteOnly ? (
                      <span className="absolute left-1 top-1 rounded-full bg-amber-500/90 px-1.5 py-0.5 text-[10px] text-white">
                        信息不全
                      </span>
                    ) : (
                      <span
                        aria-label="信息不全"
                        title="信息不全"
                        className="absolute left-1 top-1 h-2 w-2 rounded-full bg-amber-500/90"
                      />
                    ))}
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
                    className={`card-delete pointer-events-auto absolute right-1 top-1 z-10 flex min-h-7 min-w-12 items-center justify-center rounded-full p-1.5 text-[10px] leading-none text-white transition-colors transition-opacity after:absolute after:-inset-1.5 after:content-[''] disabled:opacity-40 ${
                      confirmingId === item.id ? 'bg-red-600 opacity-100' : 'bg-black/65 opacity-60 hover:opacity-100'
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
