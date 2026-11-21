/**
 * BYOK：key 只在浏览器里存，只通过请求头 X-LLM-Key 发给自己的后端。
 * 走 adapters 层是因为 core 不许碰 window / localStorage。
 * 明文存 localStorage 是既定取舍（见 DECISIONS），不做加密。
 */

const STORAGE_KEY = 'ew.llmKey'

export function getLlmKey(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setLlmKey(key: string): void {
  try {
    const trimmed = key.trim()
    if (trimmed) localStorage.setItem(STORAGE_KEY, trimmed)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* 隐私模式等场景下写不进去，当作未配置 */
  }
}

export function clearLlmKey(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}
