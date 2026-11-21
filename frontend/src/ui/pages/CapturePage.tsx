import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, RefObject } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { createItem } from '../../core/api'
import { appendDrafts, makeDraftId } from '../../core/drafts'
import { CATEGORIES, OCCASIONS, WARMTHS } from '../../core/labels'
import { isTextEntry, resolveShortcut } from '../../core/shortcuts'
import type { Category, Occasion, Warmth } from '../../core/types'
import { createPreview, releasePreview } from '../../adapters/image'
import { uploadImageFile } from '../../adapters/upload'
import { toast } from '../../adapters/toast'

interface Draft {
  id: string
  file: File
  preview: string
  category: Category | null
  warmth: Warmth | null
  occasion: Occasion | null
}

function newDraft(file: File): Draft {
  return {
    id: makeDraftId(),
    file,
    preview: createPreview(file),
    category: null,
    warmth: null,
    occasion: null,
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
export default function CapturePage({ onOpenGallery }: { onOpenGallery: () => void }) {
  const queryClient = useQueryClient()
  const containerRef = useRef<HTMLDivElement>(null)
  // 两个入口：拍照走相机、相册走文件选择（capture 与 multiple 不能同时保证行为一致）
  const cameraRef = useRef<HTMLInputElement>(null)
  const albumRef = useRef<HTMLInputElement>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [saved, setSaved] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const current = drafts[0] ?? null

  const addFiles = useCallback((files: File[]) => {
    if (files.length === 0) return
    setDrafts((prev) => appendDrafts(prev, files, newDraft))
    setError(null)
  }, [])

  const patch = useCallback((changes: Partial<Draft>) => {
    setDrafts((prev) => (prev.length === 0 ? prev : [{ ...prev[0], ...changes }, ...prev.slice(1)]))
  }, [])

  const dropCurrent = useCallback(() => {
    setDrafts((prev) => {
      if (prev.length === 0) return prev
      releasePreview(prev[0].preview)
      return prev.slice(1)
    })
  }, [])

  const save = useCallback(async () => {
    if (!current || busy) return
    if (!current.category) {
      toast('先选一个品类')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const image = await uploadImageFile(current.file)
      await createItem({
        category: current.category,
        warmth: current.warmth,
        occasion: current.occasion,
        image_ids: [image.id],
      })
      await queryClient.invalidateQueries({ queryKey: ['items'] })
      setSaved((n) => n + 1)
      dropCurrent()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }, [busy, current, dropCurrent, queryClient])

  // 键盘快捷：1-6 品类，Q/W/E 厚薄，Enter 保存，Backspace 跳过
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      if (isTextEntry(event.target)) return
      if (!current) return

      const action = resolveShortcut(event.key)
      if (!action) return
      event.preventDefault()

      if (action.type === 'category') patch({ category: action.value })
      else if (action.type === 'warmth') patch({ warmth: action.value })
      else if (action.type === 'save') void save()
      else dropCurrent()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [current, dropCurrent, patch, save])

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
    <div ref={containerRef} tabIndex={-1} className="space-y-4 outline-none">
      {current ? (
        <>
          <div className="relative overflow-hidden rounded-2xl bg-black/5">
            <img src={current.preview} alt="待录入单品" className="aspect-square w-full object-cover" />
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
            <p className="mb-2 text-xs font-medium text-black/50">品类（1-6）</p>
            <div className="grid grid-cols-3 gap-2">
              {CATEGORIES.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => patch({ category: c.value })}
                  className={`flex flex-col items-center gap-1 rounded-xl border py-3 text-sm transition ${
                    current.category === c.value
                      ? 'border-black bg-black text-white'
                      : 'border-black/10 bg-white text-black/80'
                  }`}
                >
                  <span className="text-xl">{c.icon}</span>
                  {c.label}
                </button>
              ))}
            </div>
          </section>

          <section>
            <p className="mb-2 text-xs font-medium text-black/50">厚薄（Q/W/E）</p>
            <div className="grid grid-cols-3 gap-2">
              {WARMTHS.map((w) => (
                <button
                  key={w.value}
                  type="button"
                  onClick={() => patch({ warmth: w.value })}
                  className={`rounded-xl border py-2 text-sm transition ${
                    current.warmth === w.value
                      ? 'border-black bg-black text-white'
                      : 'border-black/10 bg-white text-black/80'
                  }`}
                >
                  {w.label}
                </button>
              ))}
            </div>
          </section>

          <section>
            <p className="mb-2 text-xs font-medium text-black/50">场合</p>
            <div className="grid grid-cols-4 gap-2">
              {OCCASIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => patch({ occasion: o.value })}
                  className={`rounded-xl border py-2 text-sm transition ${
                    current.occasion === o.value
                      ? 'border-black bg-black text-white'
                      : 'border-black/10 bg-white text-black/80'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </section>

          {error && <p className="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy}
              className="flex-1 rounded-xl bg-black py-3 text-sm font-medium text-white disabled:opacity-40"
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
              <button type="button" onClick={onOpenGallery} className="ml-2 underline">
                看图库
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
