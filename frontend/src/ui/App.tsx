import { useState } from 'react'
import CapturePage from './pages/CapturePage'
import GalleryPage from './pages/GalleryPage'
import OutfitPage from './pages/OutfitPage'
import Toast from './components/Toast'

type Tab = 'capture' | 'gallery' | 'outfit'

const TABS: { value: Tab; label: string }[] = [
  { value: 'capture', label: '录入' },
  { value: 'gallery', label: '图库' },
  { value: 'outfit', label: '搭配' },
]

export default function App() {
  const [tab, setTab] = useState<Tab>('capture')

  return (
    <div className="mx-auto flex min-h-full max-w-xl flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-black/5 bg-paper/90 px-4 py-3 backdrop-blur">
        <h1 className="text-base font-semibold tracking-tight">电子衣柜</h1>
        <nav className="flex gap-1 rounded-full bg-black/5 p-1 text-sm">
          {TABS.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setTab(item.value)}
              className={`rounded-full px-3 py-1 transition ${
                tab === item.value ? 'bg-white shadow-sm' : 'text-black/60'
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="flex-1 px-4 py-4">
        {tab === 'capture' && <CapturePage onOpenGallery={() => setTab('gallery')} />}
        {tab === 'gallery' && <GalleryPage />}
        {tab === 'outfit' && <OutfitPage />}
      </main>

      <Toast />
    </div>
  )
}
