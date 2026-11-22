import { CATEGORY_LABEL } from '../../core/labels'
import type { Category, RecommendOutfit } from '../../core/types'

interface OutfitCardProps {
  outfit: RecommendOutfit
  onSave?: () => void
  saved?: boolean
  saving?: boolean
  onReroll?: () => void
  rerolling?: boolean
}

/** 一套搭配：图 + 理由 +（可选）保存 / 换一套。搭配页和对话页共用。 */
export default function OutfitCard({
  outfit,
  onSave,
  saved = false,
  saving = false,
  onReroll,
  rerolling = false,
}: OutfitCardProps) {
  return (
    <article className="space-y-2 rounded-2xl bg-white p-3 shadow-sm">
      <div className="flex gap-1.5 overflow-x-auto pb-0.5">
        {outfit.items.map((item) => (
          <div
            key={item.id}
            className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-black/5 text-lg"
          >
            {item.thumb_url ? (
              <img
                src={item.thumb_url}
                alt={CATEGORY_LABEL[item.category as Category] ?? item.category}
                className="h-full w-full object-cover"
              />
            ) : (
              <span>🧺</span>
            )}
          </div>
        ))}
      </div>

      <p className="text-sm leading-5 text-black/70">
        {outfit.relaxed_occasion && (
          <span className="mr-1.5 inline-block rounded-full bg-amber-50 px-1.5 py-0.5 text-xs text-amber-700 ring-1 ring-inset ring-amber-200 align-middle">
            通用款
          </span>
        )}
        {outfit.reason}
      </p>

      {onSave && (
        <button
          type="button"
          onClick={onSave}
          disabled={saved || saving}
          className={`w-full rounded-xl py-2.5 text-sm font-medium transition ${
            saved ? 'bg-black/5 text-black/40' : 'bg-black text-white disabled:opacity-40'
          }`}
        >
          {saved ? '已保存' : saving ? '保存中…' : '就穿这套'}
        </button>
      )}

      {onReroll && (
        <button
          type="button"
          onClick={onReroll}
          disabled={rerolling}
          className="w-full rounded-xl border border-black/10 py-2 text-sm text-black/60 disabled:opacity-40"
        >
          {rerolling ? '换一套中…' : '换一套'}
        </button>
      )}
    </article>
  )
}
