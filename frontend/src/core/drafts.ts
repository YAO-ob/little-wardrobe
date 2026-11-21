/** 草稿队列的纯逻辑：把新选的文件追加到队列，空数组时原样返回。 */

export function appendDrafts<T>(
  prev: T[],
  files: readonly File[],
  make: (file: File) => T,
): T[] {
  if (files.length === 0) return prev
  return [...prev, ...files.map(make)]
}

/**
 * 生成草稿 id。
 * crypto.randomUUID 只在安全上下文（https / localhost）存在；
 * 手机通过 http://<局域网IP>:5173 访问时它是 undefined，直接调用会抛 TypeError
 * 把整页打崩（白屏）。所以这里做降级。
 * 注意：crypto 必须在函数里取，不能在模块顶层读，避免 SSR / 测试环境差异。
 */
export function makeDraftId(): string {
  const c = globalThis.crypto as Crypto | undefined
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}
