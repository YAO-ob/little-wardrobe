import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, RefObject } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { classifyImage, createItem, deleteImage } from '../../core/api'
import {
  chooseCategory,
  chooseWarmth,
  mergeSuggestion,
  type FieldSource,
  type Suggestion,
} from '../../core/capturePrefill'
import { appendDrafts, makeDraftId } from '../../core/drafts'
import { resolveImageId } from '../../core/uploadOnce'
import { CATEGORIES, WARMTHS } from '../../core/labels'
import { isTextEntry, resolveShortcut } from '../../core/shortcuts'
import type { Category, Occasion, Warmth } from '../../core/types'
import { createPreview, releasePreview } from '../../adapters/image'
import { uploadImageFile } from '../../adapters/upload'
import { getAutoClassify, getLlmKey } from '../../adapters/autoClassify'
import { toast } from '../../adapters/toast'

type UploadState = 'idle' | 'uploading' | 'done' | 'failed'

interface Draft {
  id: string
  file: File
  preview: string
  category: Category | null
  warmth: Warmth | null
  occasion: Occasion[]
  categorySource: FieldSource | null
  warmthSource: FieldSource | null
  // 识别给的颜色家族；录入页没有颜色按钮（不为它牺牲「三次点击」），保存时直接采用
  colorFamily: string | null
  // 选图后立刻上传拿到的 id；失败或关掉识别时为 null，退回「保存时才上传」
  imageId: number | null
  uploadState: UploadState
  suggestion: Suggestion | null
}

function newDraft(file: File): Draft {
  return {
    id: makeDraftId(),
    file,
    preview: createPreview(file),
    category: null,
    warmth: null,
    occasion: [],
    categorySource: null,
    warmthSource: null,
    colorFamily: null,
    imageId: null,
    uploadState: 'idle',
    suggestion: null,
  }
}

/** 会吃掉字符键的「文本类」输入；file/button/checkbox 等一律不拦。 */

interface CaptureEntryProps {
  cameraRef: RefObject<HTMLInputElement | null>
  albumRef: RefObject<HTMLInputElement | null>
  onPick: (event: ChangeEvent<HTMLInputElement>) => void
  compact?: boolean
}

/**
 * 两个入口用 <label> 包住 input：靠 label 的原生行为激活文件选择。
 * 不用 JS `input.click()`——部分安卓 WebView / 厂商浏览器会把它判成非用户手势而静默失败。
 */
function CaptureEntry({ cameraRef, albumRef, onPick, compact = false }: CaptureEntryProps) {
  const base = compact
    ? 'flex cursor-pointer items-center justify-center rounded-xl border border-black/10 bg-white px-3 py-3 text-sm text-black/70'
    : 'flex aspect-square cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-black/15 bg-white/60 text-black/50'
  return (
    <>
      <label role="button" aria-label="拍照" className={base}>
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          onChange={onPick}
        />
        <span className={compact ? 'text-base' : 'text-4xl'}>📷</span>
        {!compact && <span className="text-sm">拍照</span>}
      </label>

      <label role="button" aria-label="从相册选" className={base}>
        <input
          ref={albumRef}
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          onChange={onPick}
        />
        <span className={compact ? 'text-base' : 'text-4xl'}>🖼</span>
        {!compact && <span className="text-sm">从相册选</span>}
      </label>
    </>
  )
}
export default function CapturePage({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const containerRef = useRef<HTMLDivElement>(null)
  // 两个入口：拍照走相机、相册走文件选择（capture 与 multiple 不能同时保证行为一致）
  const cameraRef = useRef<HTMLInputElement>(null)
  const albumRef = useRef<HTMLInputElement>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [saved, setSaved] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [autoClassify] = useState(() => getAutoClassify())
  // 同一时刻只跑一条「上传 → 分类」流水线
  const pipelineRef = useRef<string | null>(null)
  // 在途上传的 promise（解析为 image id，失败为 null）。
  // save 必须等待它，否则会双传并留孤儿——见下方 save() 的注释。
  const uploadPromiseRef = useRef<Promise<number | null> | null>(null)
  // 已经被保存掉的草稿 id：上传完成后不再浪费一次识别调用
  const consumedRef = useRef<Set<string>>(new Set())

  const current = drafts[0] ?? null

  const addFiles = useCallback((files: File[]) => {
    if (files.length === 0) return
    setDrafts((prev) => appendDrafts(prev, files, newDraft))
    setError(null)
  }, [])

  const updateById = useCallback((id: string, fn: (draft: Draft) => Draft) => {
    setDrafts((prev) => prev.map((draft) => (draft.id === id ? fn(draft) : draft)))
  }, [])

  const removeHead = useCallback(
    (discardStagedImage: boolean) => {
      const dropped = current
      setDrafts((prev) => {
        if (prev.length === 0) return prev
        releasePreview(prev[0].preview)
        return prev.slice(1)
      })
      // 提前传过又没建成单品 → 删掉暂存图，不留孤儿。
      // 保存成功时不能删：那张图已经挂到单品上了，DELETE 会 409。
      if (discardStagedImage && dropped?.imageId) {
        void deleteImage(dropped.imageId).catch(() => {
          /* 清理失败不打扰用户，最长 24 小时会被启动清理带走 */
        })
      }
    },
    [current],
  )

  const dropCurrent = useCallback(() => removeHead(true), [removeHead])

  // 队列第一张：上传 → 分类，一次只跑一条
  useEffect(() => {
    const head = drafts[0]
    if (!head || !autoClassify) return
    if (head.uploadState !== 'idle') return
    if (pipelineRef.current === head.id) return

    pipelineRef.current = head.id
    updateById(head.id, (draft) => ({ ...draft, uploadState: 'uploading' }))

    // 把在途上传存成 promise：save() 要等它，不能自己再传一次
    const uploadPromise = uploadImageFile(head.file)
      .then((image) => image.id)
      .catch(() => null)
    uploadPromiseRef.current = uploadPromise

    void (async () => {
      const uploadedId = await uploadPromise
      if (uploadedId === null) {
        updateById(head.id, (draft) => ({ ...draft, uploadState: 'failed' }))
        uploadPromiseRef.current = null
        pipelineRef.current = null
        return
      }

      updateById(head.id, (draft) => ({ ...draft, imageId: uploadedId, uploadState: 'done' }))

      // 这张已经被 Enter 保存掉了，不用再花钱识别
      if (consumedRef.current.has(head.id)) return

      try {
        const result = await classifyImage(uploadedId, getLlmKey() || undefined)
        if (result.source !== 'llm') return

        const suggestion: Suggestion = {
          category: (result.category as Category | null) ?? null,
          warmth: (result.warmth as Warmth | null) ?? null,
        }
        updateById(head.id, (draft) => ({
          ...mergeSuggestion(draft, suggestion),
          suggestion,
          colorFamily: result.color_family ?? draft.colorFamily,
          // 场合由 AI 预填，录入页不再让用户选；空数组 = 看不清 / 任何场合可用
          occasion: result.occasion ?? draft.occasion,
        }))
      } catch {
        // 识别失败静默降级，不影响录入
      } finally {
        uploadPromiseRef.current = null
        pipelineRef.current = null
      }
    })()
  }, [autoClassify, drafts, updateById])

  const save = useCallback(async () => {
    if (!current || busy) return

    // 用户没选就采纳建议值——这是「一次 Enter 就存」的关键
    const category = current.category ?? current.suggestion?.category ?? null
    const warmth = current.warmth ?? current.suggestion?.warmth ?? null
    if (!category) {
      toast('先选一个品类')
      return
    }

    setBusy(true)
    setError(null)

    // save 必须等待在途上传，否则会双传并留孤儿：
    // 选图后立刻按 Enter 时，流水线正在传，这里若直接再传一次，
    // 先传完的那张就没人认领，永久留在 media/tmp。
    let imageId: number
    let uploadedNow: boolean
    try {
      const resolved = await resolveImageId(
        current.imageId,
        uploadPromiseRef.current,
        async () => (await uploadImageFile(current.file)).id,
      )
      imageId = resolved.id
      uploadedNow = resolved.uploadedNow
    } catch (err) {
      setError(err instanceof Error ? err.message : '上传失败')
      setBusy(false)
      return
    }

    try {
      await createItem({
        category,
        warmth,
        occasion: current.occasion,
        color_family: current.colorFamily ?? undefined,
        image_ids: [imageId],
      })
      await queryClient.invalidateQueries({ queryKey: ['items'] })
      setSaved((n) => n + 1)
      // 图已挂到单品上，不能再删暂存图（DELETE 会 409）
      consumedRef.current.add(current.id)
      removeHead(false)
    } catch (err) {
      // 建单品失败且图是提前传的 → 清掉暂存图
      if (!uploadedNow && imageId !== null) {
        void deleteImage(imageId).catch(() => {})
      }
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }, [busy, current, removeHead, queryClient])

  const pickCategory = useCallback((value: Category) => {
    setDrafts((prev) => (prev.length === 0 ? prev : [chooseCategory(prev[0], value), ...prev.slice(1)]))
  }, [])

  const pickWarmth = useCallback((value: Warmth) => {
    setDrafts((prev) => (prev.length === 0 ? prev : [chooseWarmth(prev[0], value), ...prev.slice(1)]))
  }, [])

  // 键盘快捷：1-6 品类，Q/W/E 厚薄，Enter 保存，Backspace 跳过
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (isTextEntry(event.target)) return
      if (!current) return

      const action = resolveShortcut(event.key)
      if (!action) return
      event.preventDefault()

      if (action.type === 'category') pickCategory(action.value)
      else if (action.type === 'warmth') {
        // 配饰没有厚薄概念，Q/W/E 直接忽略
        if (current.category !== 'accessory') pickWarmth(action.value)
      } else if (action.type === 'save') void save()
      else dropCurrent()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [current, dropCurrent, pickCategory, pickWarmth, save])

  const remaining = drafts.length

  const hint = useMemo(() => '1-6 选品类 · Q/W/E 选厚薄 · Enter 保存 · Backspace 跳过', [])

  function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    // 必须先快照成数组：下面会把 input.value 清空，FileList 是活引用，清空后就空了。
    // （桌面 Chrome 有时保留旧引用，iOS / 部分安卓 WebView 会直接拿到空数组。）
    const input = event.currentTarget
    const picked = Array.from(input.files ?? [])

    // 只有真拿到文件才清空，否则 150ms 的兜底重读永远读不到东西
    if (picked.length > 0) input.value = ''
    // 选完立刻把焦点从 file input 上摘掉：
    // 否则字符键会被守卫拦下，Enter 还会触发浏览器默认的「再开一次文件选择框」
    input.blur()
    containerRef.current?.focus({ preventScroll: true })
    addFiles(picked)

    if (picked.length > 0) return

    // 有些 WebView 的 change 早于文件就绪：稍后再读一次，仍空才提示
    window.setTimeout(() => {
      const late = Array.from(input.files ?? [])
      input.value = ''
      if (late.length > 0) addFiles(late)
      else toast('没有取到图片，请再试一次')
    }, 150)
  }

  return (
    <div className="sheet-enter fixed inset-0 z-50 overflow-y-auto bg-paper">
      <div className="mx-auto max-w-xl px-4 py-4 pb-24">
        <div className="mb-3 flex items-center justify-between">
          <button type="button" onClick={onClose} className="text-sm text-black/50">
            ← 返回
          </button>
          <span className="text-sm font-medium">录入</span>
          <span className="w-10" />
        </div>
        <div ref={containerRef} tabIndex={-1} className="space-y-4 outline-none">
          {current ? (
            <>
              <div className="relative overflow-hidden rounded-2xl bg-black/5">
                <img src={current.preview} alt="待录入单品" className="max-h-[34vh] w-full object-contain" />
                <span className="absolute left-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-[11px] text-white">
                  待录入 {remaining}
                </span>
              </div>

              <div className="flex gap-2 overflow-x-auto pb-1">
                {drafts.slice(0, 8).map((draft, index) => (
                  <button
                    key={draft.id}
                    type="button"
                    onClick={() => {
                      if (index === 0) return
                      setDrafts((prev) => {
                        const next = [...prev]
                        const [picked] = next.splice(index, 1)
                        next.unshift(picked)
                        return next
                      })
                    }}
                    className={`h-12 w-12 shrink-0 overflow-hidden rounded-lg border-2 ${
                      index === 0 ? 'border-black' : 'border-transparent opacity-70'
                    }`}
                  >
                    <img src={draft.preview} alt="" className="h-full w-full object-cover" />
                  </button>
                ))}
                {remaining > 8 && (
                  <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-black/5 text-xs text-black/50">
                    +{remaining - 8}
                  </span>
                )}
              </div>

              <section>
                <p className="mb-2 flex items-center gap-2 text-xs font-medium text-black/50">
                  品类（1-6）
                  {autoClassify && current.uploadState === 'uploading' && (
                    <span className="text-[11px] font-normal text-black/35">正在识别…</span>
                  )}
                </p>
                <div className="grid grid-cols-3 gap-2">
                  {CATEGORIES.map((c) => {
                    const suggested =
                      current.categorySource !== 'user' && current.suggestion?.category === c.value
                    const selected = current.category === c.value
                    return (
                      <button
                        key={c.value}
                        type="button"
                        onClick={() => pickCategory(c.value)}
                        className={`relative flex flex-col items-center gap-1 rounded-xl border py-3 text-sm transition ${
                          selected
                            ? 'border-black bg-black text-white'
                            : suggested
                              ? 'border-dashed border-black/40 bg-white text-black/60'
                              : 'border-black/10 bg-white text-black/80'
                        }`}
                      >
                        <span className="text-xl">{c.icon}</span>
                        {c.label}
                        {suggested && !selected && (
                          <span className="absolute right-1 top-1 rounded-full bg-black/10 px-1.5 py-0.5 text-[9px] leading-none text-black/50">
                            建议
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              </section>

              {current.category !== 'accessory' && (
                <section>
                  <p className="mb-2 text-xs font-medium text-black/50">厚薄（Q/W/E）</p>
                <div className="grid grid-cols-3 gap-2">
                  {WARMTHS.map((w) => {
                    const suggested =
                      current.warmthSource !== 'user' && current.suggestion?.warmth === w.value
                    const selected = current.warmth === w.value
                    return (
                      <button
                        key={w.value}
                        type="button"
                        onClick={() => pickWarmth(w.value)}
                        className={`relative rounded-xl border py-2 text-sm transition ${
                          selected
                            ? 'border-black bg-black text-white'
                            : suggested
                              ? 'border-dashed border-black/40 bg-white text-black/60'
                              : 'border-black/10 bg-white text-black/80'
                        }`}
                      >
                        {w.label}
                        {suggested && !selected && (
                          <span className="absolute right-1 top-0.5 rounded-full bg-black/10 px-1 py-0.5 text-[9px] leading-none text-black/50">
                            建议
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
                </section>
              )}

              {error && <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void save()}
                  disabled={busy}
                  className="min-w-[6.5rem] flex-1 rounded-xl bg-black px-3 py-3 text-sm font-medium text-white disabled:opacity-40"
                >
                  {busy ? '保存中…' : `保存${saved > 0 ? `（已存 ${saved}）` : ''}`}
                </button>
                <CaptureEntry
                  cameraRef={cameraRef}
                  albumRef={albumRef}
                  onPick={onPick}
                  compact
                />
                <button
                  type="button"
                  onClick={dropCurrent}
                  className="rounded-xl border border-black/10 bg-white px-4 py-3 text-sm text-black/50"
                >
                  跳过
                </button>
              </div>
            </>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2">
                <CaptureEntry cameraRef={cameraRef} albumRef={albumRef} onPick={onPick} />
              </div>
              <p className="text-center text-xs text-black/40">{hint}</p>
              <div className="rounded-xl bg-black/5 px-3 py-2 text-center text-xs text-black/50">
                本次已录入 {saved} 件
                {saved > 0 && (
                  <button type="button" onClick={onClose} className="ml-2 underline">
                    看衣柜
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
