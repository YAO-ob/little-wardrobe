type Listener = (message: string) => void

const listeners = new Set<Listener>()

/** 发一条轻提示，由 UI 层的 Toast 组件消费。 */
export function toast(message: string): void {
  for (const listener of listeners) listener(message)
}

export function subscribeToast(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
