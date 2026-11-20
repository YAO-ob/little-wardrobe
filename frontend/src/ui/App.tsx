import { useState } from 'react'
import CapturePage from './pages/CapturePage'
import GalleryPage from './pages/GalleryPage'
import Toast from './components/Toast'

type Tab = 'capture' | 'gallery'

export default function App() {
  const [tab, setTab] = useState<Tab>('capture')

  return (
    <div className="mx-auto flex min-h-full max-w-xl flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-black/5 bg-paper/90 px-4 py-3 backdrop-blur">
        <h1 className="text-base font-semibold tracking-tight">电子衣柜</h1>
        <nav className="flex gap-1 rounded-full bg-black/5 p-1 text-sm">
          <button
            type="button"
            onClick={() => setTab('capture')}
            className={`rounded-full px-3 py-1 transition ${
              tab === 'capture' ? 'bg-white shadow-sm' : 'text-black/60'
            }`}
          >
            录入
          </button>
          <button
            type="button"
            onClick={() => setTab('gallery')}
            className={`rounded-full px-3 py-1 transition ${
              tab === 'gallery' ? 'bg-white shadow-sm' : 'text-black/60'
            }`}
          >
            图库
          </button>
        </nav>
      </header>

      <main className="flex-1 px-4 py-4">
        {tab === 'capture' ? (
          <CapturePage onOpenGallery={() => setTab('gallery')} />
        ) : (
          <GalleryPage />
        )}
      </main>

      <Toast />
    </div>
  )
}
