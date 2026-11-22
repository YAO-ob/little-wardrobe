import { useState, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { deleteItem, extractReceipt, updateItem } from '../../core/api'
import { buildItemPatch, validateItemForm, type ItemFormValues } from '../../core/itemPatch'
import { visibleFields } from '../../core/itemFields'
import { mergeReceipt } from '../../core/receiptMerge'
import {
  CARE_EXCLUSIVE_GROUPS,
  CARE_SYMBOLS,
  CATEGORIES,
  COLOR_OPTIONS,
  OCCASIONS,
  WARMTHS,
} from '../../core/labels'
import type { Item } from '../../core/types'
import { getLlmKey } from '../../adapters/llmKey'
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
    category: item.category,
    warmth: item.warmth == null ? '' : String(item.warmth),
    occasion: item.occasion ?? '',
    color_family: item.color_family ?? '',
    brand: item.brand ?? '',
    material: item.material ?? '',
    formality: item.formality == null ? '' : String(item.formality),
    layer: item.layer ?? '',
    season: item.season ?? [],
    price: item.price == null ? '' : String(item.price),
    note: item.note ?? '',
    size: item.size ?? '',
    purchase_url: item.purchase_url ?? '',
    care_text: item.care_text ?? '',
    care_symbols: item.care_symbols ?? [],
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
  const [recognizing, setRecognizing] = useState(false)
  const [recognized, setRecognized] = useState<Set<string>>(new Set())
  const [receiptNotice, setReceiptNotice] = useState<string | null>(null)
  const receiptInputRef = useRef<HTMLInputElement>(null)
  // 切品类立刻重算：隐藏的字段只是不渲染，值仍留在 form 里、也不会进 patch
  const visible = visibleFields(form.category)

  function update<K extends keyof ItemFormValues>(key: K, value: ItemFormValues[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
    setRecognized((prev) => {
      if (!prev.has(key)) return prev
      const next = new Set(prev)
      next.delete(key)
      return next
    })
    setErrors((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  function mark(key: string) {
    if (!recognized.has(key)) return null
    return (
      <span className="ml-1 rounded bg-black/10 px-1 py-0.5 text-[9px] leading-none text-black/50">
        识别
      </span>
    )
  }

  async function handleReceipt(file: File | null | undefined) {
    if (!file) return
    setReceiptNotice(null)
    setRecognizing(true)
    try {
      const result = await extractReceipt(file, getLlmKey() || undefined)
      if (result.source !== 'llm') {
        setReceiptNotice(
          result.reason === 'no_key'
            ? '没配置 API key，暂时无法识别'
            : '没能识别出信息，可以手动填写',
        )
        return
      }
      const merged = mergeReceipt(
        {
          brand: form.brand,
          price: form.price,
          material: form.material,
          color_family: form.color_family,
          size: form.size,
        },
        result,
      )
      setForm((prev) => ({ ...prev, ...merged.form }))
      setRecognized(new Set(merged.filled))
      if (merged.filled.length === 0) {
        setReceiptNotice('识别到的字段你都已经填了，没有覆盖')
      }
    } catch (err) {
      setReceiptNotice(err instanceof Error ? err.message : '识别失败')
    } finally {
      setRecognizing(false)
    }
  }

  function toggleSeason(value: string) {
    update(
      'season',
      form.season.includes(value)
        ? form.season.filter((item2) => item2 !== value)
        : [...form.season, value],
    )
  }

  function toggleCare(value: string) {
    if (form.care_symbols.includes(value)) {
      update(
        'care_symbols',
        form.care_symbols.filter((code) => code !== value),
      )
      return
    }
    // 同组只留一个：选新的就顶掉旧的
    const group = CARE_EXCLUSIVE_GROUPS.find((codes) => codes.includes(value)) ?? []
    const kept = form.care_symbols.filter((code) => !group.includes(code))
    update('care_symbols', [...kept, value])
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
          <p className="text-[11px] text-black/40">
            {item.created_at ? item.created_at.slice(0, 10) : ''}
          </p>
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

        <section className="mb-3 space-y-2">
          <div>
            <p className="mb-1 text-[11px] text-black/50">品类（决定在搭配里的角色）</p>
            <div className="grid grid-cols-3 gap-1.5">
              {CATEGORIES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => update('category', option.value)}
                  className={`flex flex-col items-center gap-0.5 rounded-xl border py-2 text-xs ${
                    form.category === option.value
                      ? 'border-black bg-black text-white'
                      : 'border-black/10 bg-white text-black/70'
                  }`}
                >
                  <span className="text-base leading-none">{option.icon}</span>
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {visible.has('warmth') && (
            <div>
              <p className="mb-1 text-[11px] text-black/50">厚薄（决定温度匹配）</p>
              <div className="grid grid-cols-4 gap-1.5">
              {WARMTHS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => update('warmth', String(option.value))}
                  className={`rounded-xl border py-1.5 text-xs ${
                    form.warmth === String(option.value)
                      ? 'border-black bg-black text-white'
                      : 'border-black/10 bg-white text-black/70'
                  }`}
                >
                  {option.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => update('warmth', '')}
                className={`rounded-xl border py-1.5 text-xs ${
                  form.warmth === ''
                    ? 'border-black bg-black text-white'
                    : 'border-black/10 bg-white text-black/70'
                }`}
              >
                不填
              </button>
            </div>
            </div>
          )}

          <div>
            <p className="mb-1 text-[11px] text-black/50">场合（决定筛选）</p>
            <div className="grid grid-cols-5 gap-1.5">
              {OCCASIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => update('occasion', option.value)}
                  className={`rounded-xl border py-1.5 text-xs ${
                    form.occasion === option.value
                      ? 'border-black bg-black text-white'
                      : 'border-black/10 bg-white text-black/70'
                  }`}
                >
                  {option.label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => update('occasion', '')}
                className={`rounded-xl border py-1.5 text-xs ${
                  form.occasion === ''
                    ? 'border-black bg-black text-white'
                    : 'border-black/10 bg-white text-black/70'
                }`}
              >
                不填
              </button>
            </div>
          </div>
        </section>

        <div className="mb-3 space-y-1">
          <input
            ref={receiptInputRef}
            type="file"
            accept="image/*"
            className="sr-only"
            onChange={(event) => {
              const picked = event.target.files?.[0] ?? null
              event.target.value = ''
              void handleReceipt(picked)
            }}
          />
          <button
            type="button"
            onClick={() => receiptInputRef.current?.click()}
            disabled={recognizing}
            className="w-full rounded-xl border border-dashed border-black/20 py-2 text-sm text-black/60 disabled:opacity-40"
          >
            {recognizing ? '正在识别…' : '从截图识别'}
          </button>
          <p className="text-[11px] text-black/35">截图会发送给你配置的模型服务商</p>
          {receiptNotice && <p className="text-[11px] text-amber-700">{receiptNotice}</p>}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">颜色 {mark('color_family')}</span>
            <select
              value={form.color_family}
              onChange={(event) => update('color_family', event.target.value)}
              className={fieldClass}
            >
              <option value="">不填</option>
              {COLOR_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">品牌 {mark('brand')}</span>
            <input
              value={form.brand}
              onChange={(event) => update('brand', event.target.value)}
              className={fieldClass}
            />
          </label>

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">材质 {mark('material')}</span>
            <input
              value={form.material}
              onChange={(event) => update('material', event.target.value)}
              className={fieldClass}
            />
          </label>

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">价格 {mark('price')}</span>
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

          {visible.has('layer') && (
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
          )}

          {visible.has('season') && (
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
          )}

          <label className="col-span-2 space-y-1">
            <span className="text-[11px] text-black/50">备注</span>
            <input
              value={form.note}
              onChange={(event) => update('note', event.target.value)}
              className={fieldClass}
            />
          </label>

          {visible.has('size') && (
            <label className="col-span-1 space-y-1">
              <span className="text-[11px] text-black/50">尺码 {mark('size')}</span>
              <input
                value={form.size}
                onChange={(event) => update('size', event.target.value)}
                placeholder="M / 42 / One Size"
                className={fieldClass}
              />
            </label>
          )}

          <label className="col-span-1 space-y-1">
            <span className="text-[11px] text-black/50">购买链接</span>
            <input
              value={form.purchase_url}
              onChange={(event) => update('purchase_url', event.target.value)}
              placeholder="https://"
              className={fieldClass}
            />
            {/^https?:\/\//.test(form.purchase_url) && (
              <a
                href={form.purchase_url}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-blue-600 underline"
              >
                打开链接
              </a>
            )}
          </label>

          {visible.has('care_symbols') && (
            <div className="col-span-2 space-y-1">
              <span className="text-[11px] text-black/50">
                洗护符号
                {form.care_symbols.length === 0 && <span className="ml-2 text-black/30">未填</span>}
              </span>
              <div className="flex flex-wrap gap-1.5">
                {CARE_SYMBOLS.map((symbol) => {
                  const active = form.care_symbols.includes(symbol.value)
                  const group =
                    CARE_EXCLUSIVE_GROUPS.find((codes) => codes.includes(symbol.value)) ?? []
                  const blocked =
                    !active && group.some((code) => form.care_symbols.includes(code))
                  return (
                    <button
                      key={symbol.value}
                      type="button"
                      onClick={() => toggleCare(symbol.value)}
                      disabled={blocked}
                      aria-pressed={active}
                      className={`rounded-full border px-2.5 py-1 text-[11px] ${
                        active
                          ? 'border-black bg-black text-white'
                          : blocked
                            ? 'border-black/5 bg-black/5 text-black/25'
                            : 'border-black/10 bg-white text-black/60'
                      }`}
                    >
                      {symbol.label}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <label className="col-span-2 space-y-1">
            <span className="text-[11px] text-black/50">洗护说明</span>
            <textarea
              value={form.care_text}
              onChange={(event) => update('care_text', event.target.value)}
              rows={2}
              placeholder="比如：30℃ 机洗，反面晾干，不要漂白"
              className={`${fieldClass} resize-none`}
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
