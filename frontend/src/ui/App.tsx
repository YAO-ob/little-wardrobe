import { useState } from 'react'
import CapturePage from './pages/CapturePage'
import GalleryPage from './pages/GalleryPage'
import OutfitPage from './pages/OutfitPage'
import Toast from './components/Toast'

type Tab = 'capture' | 'gallery' | 'outfit'

const TABS: { value: Tab; label: string; icon: string }[] = [
  { value: 'capture', label: '录入', icon: '📷' },
  { value: 'gallery', label: '图库', icon: '🧺' },
  { value: 'outfit', label: '搭配', icon: '👕' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('capture')

  return (
    <div className="mx-auto flex min-h-full max-w-xl flex-col">
      <header className="sticky top-0 z-10 border-b border-black/5 bg-paper/90 px-4 py-3 backdrop-blur">
        <h1 className="text-base font-semibold tracking-tight">电子衣柜</h1>
      </header>

      {/* pb-24 给底部标签栏留位，最后一张卡片不会被遮住 */}
      <main className="flex-1 px-4 py-4 pb-24">
        {tab === 'capture' && <CapturePage onOpenGallery={() => setTab('gallery')} />}
        {tab === 'gallery' && <GalleryPage />}
        {tab === 'outfit' && <OutfitPage />}
      </main>

      <nav
        aria-label="主导航"
        className="fixed inset-x-0 bottom-0 z-20 mx-auto max-w-xl border-t border-black/5 bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      >
        <div className="grid grid-cols-3 px-2">
          {TABS.map((item) => {
            const active = tab === item.value
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => setTab(item.value)}
                aria-current={active ? 'page' : undefined}
                className={`relative flex min-h-14 flex-col items-center justify-center gap-0.5 py-2 text-[11px] transition-colors ${
                  active ? 'font-medium text-black' : 'text-black/45'
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`absolute inset-x-6 top-0 h-0.5 rounded-full ${
                    active ? 'bg-black' : 'bg-transparent'
                  }`}
                />
                <span className="text-lg leading-none">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            )
          })}
        </div>
      </nav>

      <Toast />
    </div>
  )
}
