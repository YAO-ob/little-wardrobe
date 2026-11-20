import { useEffect, useState } from 'react'
import { subscribeToast } from '../../adapters/toast'

export default function Toast() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => subscribeToast(setMessage), [])

  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(() => setMessage(null), 1800)
    return () => window.clearTimeout(timer)
  }, [message])

  if (!message) return null

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-30 flex justify-center">
      <p className="rounded-full bg-black/85 px-4 py-2 text-xs text-white shadow-lg">{message}</p>
    </div>
  )
}
