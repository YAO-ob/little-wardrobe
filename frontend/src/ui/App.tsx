import { useState } from 'react'
import CapturePage from './pages/CapturePage'
import GalleryPage from './pages/GalleryPage'
import OutfitPage from './pages/OutfitPage'
import ChatPage from './pages/ChatPage'
import Toast from './components/Toast'

type Tab = 'gallery' | 'outfit' | 'chat'

const TABS: { value: Tab; label: string; icon: string }[] = [
  { value: 'gallery', label: '衣柜', icon: '🗄️' },
  { value: 'outfit', label: '搭配', icon: '👕' },
  { value: 'chat', label: '问问', icon: '💬' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('gallery')
  // 录入不再占底部 tab：从衣柜页的悬浮「＋」或问问页的引导按钮打开，全屏覆盖层
  const [captureOpen, setCaptureOpen] = useState(false)

  return (
    <div className="mx-auto flex min-h-full max-w-xl flex-col">
      <header className="sticky top-0 z-10 border-b border-black/5 bg-paper/90 px-4 py-3 backdrop-blur">
        <h1 className="text-base font-semibold tracking-tight">小柜子</h1>
      </header>

      {/* pb-24 给底部标签栏留位，最后一张卡片不会被遮住 */}
      <main className="flex-1 px-4 py-4 pb-24">
        {tab === 'gallery' && <GalleryPage />}
        {tab === 'outfit' && <OutfitPage />}
        {tab === 'chat' && <ChatPage onOpenCapture={() => setCaptureOpen(true)} />}
      </main>

      {/* 衣柜页右下角悬浮入口：点开全屏录入覆盖层（覆盖层打开时它自身会被盖住，无需额外判断） */}
      {tab === 'gallery' && (
        <button
          type="button"
          onClick={() => setCaptureOpen(true)}
          aria-label="录入新衣服"
          className="fixed bottom-20 right-4 z-30 flex h-14 w-14 items-center justify-center rounded-full bg-black text-2xl text-white shadow-lg transition active:scale-95"
        >
          +
        </button>
      )}

      {captureOpen && <CapturePage onClose={() => setCaptureOpen(false)} />}

      <nav
        aria-label="主导航"
        className="fixed inset-x-0 bottom-0 z-20 mx-auto max-w-xl border-t border-black/5 bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur"
      >
        <div className="grid grid-cols-3 px-1">
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
                  className={`absolute inset-x-4 top-0 h-0.5 rounded-full ${
                    active ? 'bg-black' : 'bg-transparent'
                  }`}
                />
                <span className="text-base leading-none">{item.icon}</span>
                <span className="whitespace-nowrap">{item.label}</span>
              </button>
            )
          })}
        </div>
      </nav>

      <Toast />
    </div>
  )
}
