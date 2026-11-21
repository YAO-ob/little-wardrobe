import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getRecommend, saveOutfit } from '../../core/api'
import { CATEGORIES, CATEGORY_LABEL, OCCASIONS } from '../../core/labels'
import type { Category, Occasion, RecommendOutfit } from '../../core/types'
import { toast } from '../../adapters/toast'

const CITY = '杭州'

export default function OutfitPage() {
  const [occasion, setOccasion] = useState<Occasion>('casual')
  const [savedKeys, setSavedKeys] = useState<string[]>([])
  const [savingKey, setSavingKey] = useState<string | null>(null)

  const { data, isLoading, error, isFetching, refetch } = useQuery({
    queryKey: ['recommend', occasion],
    queryFn: () => getRecommend({ city: CITY, occasion }),
    retry: false,
    staleTime: 60_000,
  })

  async function save(outfit: RecommendOutfit, index: number) {
    const key = `${occasion}-${index}`
    if (savedKeys.includes(key) || savingKey === key || !data) return
    setSavingKey(key)
    try {
      await saveOutfit({
        item_ids: outfit.items.map((item) => item.id),
        weather: data.weather,
        note: `规则推荐 · ${occasion}`,
      })
      setSavedKeys((prev) => [...prev, key])
      toast('已记下今天的搭配')
    } catch (err) {
      toast(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSavingKey(null)
    }
  }

  if (isLoading) {
    return <p className="py-16 text-center text-sm text-black/40">正在看天气和衣橱…</p>
  }

  if (error || !data) {
    const message = error instanceof Error ? error.message : '未知错误'
    return (
      <div className="space-y-3 rounded-2xl bg-white p-4 shadow-sm">
        <p className="text-sm font-medium text-red-600">没能拿到今日推荐</p>
        <p className="text-xs leading-5 text-black/60">{message}</p>
        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="rounded-xl bg-black px-4 py-2 text-sm text-white disabled:opacity-40"
        >
          {isFetching ? '重试中…' : '重试'}
        </button>
      </div>
    )
  }

  const weather = data.weather

  return (
    <div className="space-y-3">
      <section className="rounded-2xl bg-white p-3 shadow-sm">
        <div className="flex items-baseline justify-between">
          <p className="text-sm font-medium">
            {weather.city} · {weather.weather_text}
          </p>
          <p className="text-[11px] text-black/40">{weather.date}</p>
        </div>
        <p className="mt-1 text-3xl font-semibold tracking-tight">
          {Math.round(weather.t_min)}–{Math.round(weather.t_max)}
          <span className="ml-0.5 text-base font-normal text-black/50">℃</span>
        </p>
        <p className="mt-1 text-xs text-black/50">
          体感 {Math.round(weather.feels_min)}–{Math.round(weather.feels_max)}℃ · 降水{' '}
          {Math.round(weather.precip_prob)}% · UV {weather.uv.toFixed(1)}
        </p>
        {weather.stale && (
          <p className="mt-1 text-[11px] text-amber-600">天气可能不是最新（上游暂时不可用）</p>
        )}
        <p className="mt-1 text-right text-[10px] leading-none text-black/25">
          数据来源 Open-Meteo
        </p>
      </section>

      <div className="grid grid-cols-4 gap-2">
        {OCCASIONS.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setOccasion(item.value)}
            className={`rounded-xl border py-2 text-sm transition ${
              occasion === item.value
                ? 'border-black bg-black text-white'
                : 'border-black/10 bg-white text-black/70'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {data.notice && (
        <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700">{data.notice}</p>
      )}

      {data.outfits.length === 0 && (
        <p className="py-10 text-center text-sm text-black/40">今天组不出完整搭配，先补几件衣服</p>
      )}

      {data.outfits.map((outfit, index) => {
        const key = `${occasion}-${index}`
        const isSaved = savedKeys.includes(key)
        const isSaving = savingKey === key
        return (
          <article key={key} className="space-y-2 rounded-2xl bg-white p-3 shadow-sm">
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

            <p className="text-sm leading-5 text-black/70">{outfit.reason}</p>

            <button
              type="button"
              onClick={() => void save(outfit, index)}
              disabled={isSaved || isSaving}
              className={`w-full rounded-xl py-2.5 text-sm font-medium transition ${
                isSaved
                  ? 'bg-black/5 text-black/40'
                  : 'bg-black text-white disabled:opacity-40'
              }`}
            >
              {isSaved ? '已保存' : isSaving ? '保存中…' : '就穿这套'}
            </button>
          </article>
        )
      })}

      <p className="pb-2 text-center text-[11px] text-black/30">
        搭配由规则生成（{CATEGORIES.length} 类单品 · {CITY}）· 天气数据 Open-Meteo
      </p>
    </div>
  )
}
