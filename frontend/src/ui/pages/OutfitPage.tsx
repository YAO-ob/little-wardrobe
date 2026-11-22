import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { getCities, getOutfits, getRecommend, saveOutfit } from '../../core/api'
import { CATEGORIES, OCCASIONS } from '../../core/labels'
import { DEFAULT_CITY, FALLBACK_CITIES } from '../../core/cities'
import { badgeFor, maskKey } from '../../core/recommendBadge'
import { weatherAgeText } from '../../core/weatherAge'
import type { Occasion, RecommendOutfit } from '../../core/types'
import { getLlmKey, setLlmKey, clearLlmKey } from '../../adapters/llmKey'
import { getAutoClassify, setAutoClassify } from '../../adapters/autoClassify'
import { getCity, setCity } from '../../adapters/city'
import { toast } from '../../adapters/toast'
import OutfitCard from '../components/OutfitCard'

// 模型正常 0.8–1.2s；后端最坏会等 ~10.5s（天气重试）。超过这个就退回规则，别让用户干等
const SLOW_TIMEOUT_MS = 12_000

const BADGE_CLASS: Record<string, string> = {
  ai: 'bg-black text-white',
  cache: 'bg-black/70 text-white',
  rules: 'bg-black/5 text-black/60',
}

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="h-4 w-4">
      <path
        d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="2.6" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  )
}

function EyeOffIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className="h-4 w-4">
      <path
        d="M4 4l16 16M9.9 5.7A10.6 10.6 0 0 1 12 5.5c6.5 0 10 6.5 10 6.5a17 17 0 0 1-3.1 3.8M6.4 7.9A17 17 0 0 0 2 12s3.5 6.5 10 6.5c1 0 1.9-.2 2.7-.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function OutfitPage() {
  const queryClient = useQueryClient()
  const [occasion, setOccasion] = useState<Occasion>('casual')
  const [savedKeys, setSavedKeys] = useState<string[]>([])
  const [savingKey, setSavingKey] = useState<string | null>(null)

  const [apiKey, setApiKey] = useState(() => getLlmKey())
  const [aiMode, setAiMode] = useState(false)
  const [keyVersion, setKeyVersion] = useState(0)
  const [city, setCityState] = useState<string>(() => getCity(FALLBACK_CITIES))
  const [cityOpen, setCityOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [autoClassify, setAutoClassifyState] = useState(() => getAutoClassify())
  const [draftKey, setDraftKey] = useState('')
  // 弹层两态：editing=true 显示输入框；false 显示「已配置」状态
  const [editing, setEditing] = useState(false)
  // 已配置状态下用眼睛临时看全 key（只在弹层内生效）
  const [revealSaved, setRevealSaved] = useState(false)
  // 输入框本身的明文/密码切换
  const [showDraft, setShowDraft] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const hasKey = apiKey.trim().length > 0

  const { data, isLoading, error, isFetching, refetch } = useQuery({
    queryKey: ['recommend', city, occasion, aiMode ? 'llm' : 'rules', keyVersion],
    queryFn: () =>
      getRecommend({
        city,
        occasion,
        mode: aiMode ? 'llm' : 'rules',
        llmKey: aiMode ? apiKey : undefined,
      }),
    retry: false,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })

  const outfitsQuery = useQuery({
    queryKey: ['outfits'],
    queryFn: () => getOutfits(10),
    staleTime: 30_000,
    retry: false,
  })

  // 城市列表以后端为准；接口挂了就用兜底列表，下拉不会因此不可用
  const citiesQuery = useQuery({
    queryKey: ['cities'],
    queryFn: getCities,
    staleTime: 60 * 60 * 1000,
    retry: false,
  })
  const cityList: string[] =
    citiesQuery.data?.cities && citiesQuery.data.cities.length > 0
      ? citiesQuery.data.cities
      : [...FALLBACK_CITIES]

  // 后端删了某个城市、而 localStorage 里还存着它 → 回落到默认城市
  useEffect(() => {
    if (!citiesQuery.data) return
    if (!citiesQuery.data.cities.includes(city)) {
      setCityState(citiesQuery.data.default || DEFAULT_CITY)
    }
  }, [citiesQuery.data, city])

  function chooseCity(name: string) {
    setCity(name) // 写 localStorage，刷新后仍是这个城市
    setCityState(name)
    setCityOpen(false)
  }

  // 太慢就退回规则，别让页面一直转
  useEffect(() => {
    if (!aiMode || !isFetching) return
    const timer = window.setTimeout(() => {
      setAiMode(false)
      toast('这次有点慢，先给你规则推荐')
    }, SLOW_TIMEOUT_MS)
    return () => window.clearTimeout(timer)
  }, [aiMode, isFetching])

  function openSettings() {
    setSettingsOpen(true)
    setEditing(!hasKey) // 没存过就直接给输入框；存过就先看状态
    setDraftKey('')
    setRevealSaved(false)
    setShowDraft(false)
  }

  // 展开输入框时自动聚焦
  useEffect(() => {
    if (settingsOpen && editing) inputRef.current?.focus()
  }, [settingsOpen, editing])

  function toggleAi() {
    if (!hasKey) {
      toast('先配置 API key')
      openSettings()
      return
    }
    setAiMode((value) => !value)
  }

  function saveKey() {
    const trimmed = draftKey.trim()
    if (!trimmed) {
      toast('先填一个 key')
      return
    }
    setLlmKey(trimmed)
    setApiKey(trimmed)
    setKeyVersion((value) => value + 1)
    setDraftKey('')
    setEditing(false)
    setShowDraft(false)
    setRevealSaved(false)
    setSettingsOpen(false)
    toast('已保存')
  }

  function removeKey() {
    clearLlmKey()
    setApiKey('')
    setDraftKey('')
    setAiMode(false)
    setKeyVersion((value) => value + 1)
    setEditing(false)
    setRevealSaved(false)
    setShowDraft(false)
    setSettingsOpen(false)
    toast('已清除')
  }

  async function save(outfit: RecommendOutfit, index: number) {
    const key = `${city}-${occasion}-${index}`
    if (savedKeys.includes(key) || savingKey === key || !data) return
    setSavingKey(key)
    try {
      await saveOutfit({
        item_ids: outfit.items.map((item) => item.id),
        weather: data.weather,
        note: `规则推荐 · ${occasion}`,
      })
      setSavedKeys((prev) => [...prev, key])
      await queryClient.invalidateQueries({ queryKey: ['outfits'] })
      toast('已记下今天的搭配')
    } catch (err) {
      toast(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSavingKey(null)
    }
  }

  const badge = data ? badgeFor(data) : null

  return (
    <div className="space-y-3">
      <section className="relative rounded-2xl bg-white p-3 shadow-sm">
        <div className="flex items-baseline justify-between">
          <button
            type="button"
            onClick={() => setCityOpen((value) => !value)}
            aria-label="切换城市"
            className="flex items-baseline gap-1 text-sm font-medium"
          >
            {data?.weather.city ?? city}
            {data ? <span className="text-black/40"> · {data.weather.weather_text}</span> : null}
            <span className="text-[10px] text-black/30">▾</span>
          </button>
          <p className="text-[11px] text-black/40">{data?.weather.date ?? ''}</p>
        </div>

        {cityOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setCityOpen(false)} />
            <div className="absolute left-3 top-10 z-20 w-36 overflow-hidden rounded-xl border border-black/10 bg-white shadow-lg">
              {cityList.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => chooseCity(name)}
                  className={`block w-full px-3 py-2 text-left text-sm ${
                    name === city ? 'bg-black text-white' : 'text-black/70 hover:bg-black/5'
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
          </>
        )}

        {data ? (
          <>
            <p className="mt-1 text-3xl font-semibold tracking-tight">
              {Math.round(data.weather.t_min)}–{Math.round(data.weather.t_max)}
              <span className="ml-0.5 text-base font-normal text-black/50">℃</span>
            </p>
            <p className="mt-1 text-xs text-black/50">
              体感 {Math.round(data.weather.feels_min)}–{Math.round(data.weather.feels_max)}℃ · 降水{' '}
              {Math.round(data.weather.precip_prob)}% · UV {data.weather.uv.toFixed(1)}
            </p>
            {data.weather.stale && (
              <p className="mt-1 text-[11px] text-amber-600">
                ⚠ 天气取自 {weatherAgeText(data.weather.fetched_at)}的缓存
              </p>
            )}
            <p className="mt-1 text-right text-[10px] leading-none text-black/25">
              数据来源 Open-Meteo
            </p>
          </>
        ) : (
          <p className="py-6 text-center text-sm text-black/40">
            {isLoading ? '正在看天气和衣橱…' : '天气暂时取不到'}
          </p>
        )}
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

      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={toggleAi}
          aria-disabled={!hasKey}
          className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition ${
            aiMode
              ? 'border-black bg-black text-white'
              : hasKey
                ? 'border-black/15 bg-white text-black/70'
                : 'border-black/10 bg-black/5 text-black/30'
          }`}
        >
          <span>✨</span>
          AI 精选{aiMode ? ' 开' : ' 关'}
        </button>

        <button
          type="button"
          onClick={openSettings}
          aria-label="设置"
          className="rounded-full border border-black/10 bg-white px-3 py-1.5 text-xs text-black/60"
        >
          ⚙ 设置
        </button>
      </div>

      {aiMode && isFetching && (
        <p className="animate-pulse rounded-xl bg-black px-3 py-2 text-center text-xs text-white">
          AI 正在挑衣服…
        </p>
      )}

      {badge && (
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2 py-0.5 text-[11px] ${BADGE_CLASS[badge.tone]}`}>
            {badge.label}
          </span>
          {badge.detail && <span className="text-[11px] text-black/45">{badge.detail}</span>}
          {data?.notice && (
            <span className="text-[11px] text-amber-700">{data.notice}</span>
          )}
        </div>
      )}

      {error && !data && (
        <div className="space-y-3 rounded-2xl bg-white p-4 shadow-sm">
          <p className="text-sm font-medium text-red-600">没能拿到今日推荐</p>
          <p className="text-xs leading-5 text-black/60">
            {error instanceof Error ? error.message : '未知错误'}
          </p>
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="rounded-xl bg-black px-4 py-2 text-sm text-white disabled:opacity-40"
          >
            {isFetching ? '重试中…' : '重试'}
          </button>
        </div>
      )}

      {data && data.outfits.length === 0 && (
        <p className="py-10 text-center text-sm text-black/40">
          今天组不出完整搭配，先补几件衣服
          {data.notice ? `（${data.notice}）` : ''}
        </p>
      )}

      {(data?.outfits ?? []).map((outfit, index) => {
        const key = `${city}-${occasion}-${index}`
        const isSaved = savedKeys.includes(key)
        const isSaving = savingKey === key
        return (
          <OutfitCard
            key={key}
            outfit={outfit}
            onSave={() => void save(outfit, index)}
            saved={isSaved}
            saving={isSaving}
          />
        )
      })}

      <section className="space-y-1.5 pb-1">
        <p className="text-[11px] font-medium text-black/40">最近穿过</p>
        {outfitsQuery.isLoading && <p className="text-[11px] text-black/30">加载中…</p>}
        {!outfitsQuery.isLoading && (outfitsQuery.data?.outfits.length ?? 0) === 0 && (
          <p className="text-[11px] text-black/30">还没有保存过搭配</p>
        )}
        {(outfitsQuery.data?.outfits ?? []).map((record) => (
          <div key={record.id} className="flex items-center gap-2 text-[11px] text-black/45">
            <span className="w-20 shrink-0 tabular-nums">{record.worn_on}</span>
            <div className="flex gap-1">
              {record.items.map((item) =>
                item.thumb_url ? (
                  <img
                    key={item.id}
                    src={item.thumb_url}
                    alt={item.category ?? ''}
                    loading="lazy"
                    className="h-6 w-6 rounded object-cover"
                  />
                ) : (
                  <span
                    key={item.id}
                    className="flex h-6 w-6 items-center justify-center rounded bg-black/5 text-[10px] text-black/30"
                  >
                    ?
                  </span>
                ),
              )}
            </div>
            <span>{record.item_ids.length} 件</span>
          </div>
        ))}
      </section>

      <p className="pb-2 text-center text-[11px] text-black/30">
        搭配由规则生成（{CATEGORIES.length} 类单品 · {city}）· 天气数据 Open-Meteo
      </p>

      {settingsOpen && (
        <div
          className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setSettingsOpen(false)}
        >
          <div
            className="w-full max-w-sm space-y-3 rounded-2xl bg-white p-4"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-baseline justify-between">
              <p className="text-sm font-medium">模型 API key</p>
              <button
                type="button"
                onClick={() => setSettingsOpen(false)}
                className="text-xs text-black/40"
              >
                关闭
              </button>
            </div>

            {!editing && hasKey ? (
              <>
                <div className="flex items-center gap-2">
                  <p className="flex-1 break-all text-xs text-black/60">
                    已配置（{revealSaved ? apiKey : maskKey(apiKey)}）
                  </p>
                  <button
                    type="button"
                    onClick={() => setRevealSaved((value) => !value)}
                    aria-label={revealSaved ? '隐藏 key' : '显示 key'}
                    title={revealSaved ? '隐藏 key' : '显示 key'}
                    className="rounded-lg p-1.5 text-black/50 hover:bg-black/5"
                  >
                    {/* 图标反映当前状态：看得见=睁眼，遮住=斜线眼 */}
                    {revealSaved ? <EyeIcon /> : <EyeOffIcon />}
                  </button>
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setDraftKey('')
                      setShowDraft(false)
                      setEditing(true)
                    }}
                    className="flex-1 rounded-xl bg-black py-2 text-sm text-white"
                  >
                    更换
                  </button>
                  <button
                    type="button"
                    onClick={removeKey}
                    className="rounded-xl border border-black/10 px-4 py-2 text-sm text-black/60"
                  >
                    清除
                  </button>
                </div>
              </>
            ) : (
              <>
                <p className="text-xs text-black/50">
                  {hasKey ? '更换 key' : '未配置'}
                  {!hasKey && '：在 DeepSeek 后台创建，形如 sk-...'}
                </p>

                <div className="relative">
                  <input
                    ref={inputRef}
                    type={showDraft ? 'text' : 'password'}
                    value={draftKey}
                    onChange={(event) => setDraftKey(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        saveKey()
                      }
                    }}
                    placeholder="sk-..."
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full rounded-xl border border-black/10 bg-white py-2 pl-3 pr-10 text-sm outline-none focus:border-black/30"
                  />
                  <button
                    type="button"
                    onClick={() => setShowDraft((value) => !value)}
                    aria-label={showDraft ? '隐藏 key' : '显示 key'}
                    title={showDraft ? '隐藏 key' : '显示 key'}
                    className="absolute inset-y-0 right-0 flex items-center px-2 text-black/45"
                  >
                    {/* 图标反映当前状态：看得见=睁眼，遮住=斜线眼 */}
                    {showDraft ? <EyeIcon /> : <EyeOffIcon />}
                  </button>
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={saveKey}
                    className="flex-1 rounded-xl bg-black py-2 text-sm text-white"
                  >
                    保存
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (hasKey) {
                        setEditing(false)
                        setDraftKey('')
                        setShowDraft(false)
                      } else {
                        setSettingsOpen(false)
                      }
                    }}
                    className="rounded-xl border border-black/10 px-4 py-2 text-sm text-black/60"
                  >
                    取消
                  </button>
                </div>
              </>
            )}

            <div className="flex items-center justify-between gap-3 border-t border-black/5 pt-3">
              <div>
                <p className="text-sm">录入时自动识别</p>
                <p className="text-[11px] text-black/40">选图后预填品类和厚薄，只给建议，不覆盖你的选择</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={autoClassify}
                onClick={() => {
                  const next = !autoClassify
                  setAutoClassify(next)
                  setAutoClassifyState(next)
                }}
                className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                  autoClassify ? 'bg-black' : 'bg-black/15'
                }`}
              >
                <span
                  className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${
                    autoClassify ? 'left-[1.375rem]' : 'left-0.5'
                  }`}
                />
              </button>
            </div>

            <p className="text-[11px] leading-5 text-black/40">
              key 只存在本机浏览器（localStorage），请求时通过 X-LLM-Key 发给后端，不写日志。
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
