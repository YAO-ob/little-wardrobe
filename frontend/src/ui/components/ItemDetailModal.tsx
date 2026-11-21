import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { deleteItem, updateItem } from '../../core/api'
import { buildItemPatch, validateItemForm, type ItemFormValues } from '../../core/itemPatch'
import { CATEGORY_LABEL, WARMTH_LABEL } from '../../core/labels'
import type { Category, Item } from '../../core/types'
import { toast } from '../../adapters/toast'

const LAYERS = [
  { value: '', label: '不填' },
  { value: 'inner', label: '内层' },
  { value: 'mid', label: '中层' },
  { value: 'outer', label: '外层' },
]

const SEASONS = [
  { value: 'spring', label: '春' },
  { value: 'summer', label: '夏' },
  { value: 'autumn', label: '秋' },
  { value: 'winter', label: '冬' },
]

function initialForm(item: Item): ItemFormValues {
  return {
    color_family: item.color_family ?? '',
    brand: item.brand ?? '',
    material: item.material ?? '',
    formality: item.formality == null ? '' : String(item.formality),
    layer: item.layer ?? '',
    season: item.season ?? [],
    price: item.price == null ? '' : String(item.price),
    note: item.note ?? '',
  }
}

const fieldClass =
  'w-full rounded-lg border border-black/10 bg-white px-2 py-1.5 text-sm outline-none focus:border-black/30'

export default function ItemDetailModal({ item, onClose }: { item: Item; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<ItemFormValues>(() => initialForm(item))
  const [errors, setErrors] = useState<Partial<Record<keyof ItemFormValues, string>>>({})
  const [saving, setSaving] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  function update<K extends keyof ItemFormValues>(key: K, value: ItemFormValues[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  function toggleSeason(value: string) {
    update(
      'season',
      form.season.includes(value)
        ? form.season.filter((item2) => item2 !== value)
        : [...form.season, value],
    )
  }

  async function save() {
    const found = validateItemForm(form)
    setErrors(found)
    if (Object.keys(found).length > 0) return

    const patch = buildItemPatch(form, item)
    if (Object.keys(patch).length === 0) {
      onClose()
      return
    }

    setSaving(true)
    try {
      await updateItem(item.id, patch)
      await queryClient.invalidateQueries({ queryKey: ['items'] })
      toast('已保存')
      onClose()
    } catch (err) {
      toast(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function remove() {
    if (!confirmingDelete) {
      setConfirmingDelete(true)
      return
    }
    setSaving(true)
    try {
      await deleteItem(item.id)
      await queryClient.invalidateQueries({ queryKey: ['items'] })
      toast('已删除')
      onClose()
    } catch (err) {
      toast(err instanceof Error ? err.message : '删除失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-4 sm:rounded-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-medium">{CATEGORY_LABEL[item.category as Category] ?? item.category}</p>
            <p className="text-[11px] text-black/40">
              {item.warmth ? `${WARMTH_LABEL[item.warmth]} · ` : ''}
              {item.created_at ? item.created_at.slice(0, 10) : ''}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-xs text-black/40">
            关闭
          </button>
        </div>

        {item.image?.url && (
          <img
            src={item.image.url}
            alt={item.name}
            className="mb-3 aspect-square w-full rounded-xl bg-black/5 object-cover"
          />
        )}

        <div className="grid grid-cols-2 gap-2">
          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">颜色</span>
            <input
              value={form.color_family}
              onChange={(event) => update('color_family', event.target.value)}
              placeholder="黑 / 藏青"
              className={fieldClass}
            />
          </label>

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">品牌</span>
            <input
              value={form.brand}
              onChange={(event) => update('brand', event.target.value)}
              className={fieldClass}
            />
          </label>

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">材质</span>
            <input
              value={form.material}
              onChange={(event) => update('material', event.target.value)}
              className={fieldClass}
            />
          </label>

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">价格</span>
            <input
              value={form.price}
              onChange={(event) => update('price', event.target.value)}
              inputMode="decimal"
              className={fieldClass}
            />
            {errors.price && <span className="text-[11px] text-red-600">{errors.price}</span>}
          </label>

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">正式度 1–5</span>
            <input
              value={form.formality}
              onChange={(event) => update('formality', event.target.value)}
              inputMode="numeric"
              className={fieldClass}
            />
            {errors.formality && (
              <span className="text-[11px] text-red-600">{errors.formality}</span>
            )}
          </label>

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">在搭配里的位置</span>
            <select
              value={form.layer}
              onChange={(event) => update('layer', event.target.value)}
              className={fieldClass}
            >
              {LAYERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="col-span-2 space-y-1">
            <span className="text-[11px] text-black/50">季节</span>
            <div className="flex gap-1.5">
              {SEASONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => toggleSeason(option.value)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    form.season.includes(option.value)
                      ? 'border-black bg-black text-white'
                      : 'border-black/10 bg-white text-black/60'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <label className="col-span-2 space-y-1">
            <span className="text-[11px] text-black/50">备注</span>
            <input
              value={form.note}
              onChange={(event) => update('note', event.target.value)}
              className={fieldClass}
            />
          </label>
        </div>

        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving}
            className="flex-1 rounded-xl bg-black py-2.5 text-sm text-white disabled:opacity-40"
          >
            {saving ? '保存中…' : '保存'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-black/10 px-4 py-2.5 text-sm text-black/60"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void remove()}
            disabled={saving}
            className="rounded-xl border border-red-200 px-4 py-2.5 text-sm text-red-600 disabled:opacity-40"
          >
            {confirmingDelete ? '确认删除' : '删除'}
          </button>
        </div>
      </div>
    </div>
  )
}
