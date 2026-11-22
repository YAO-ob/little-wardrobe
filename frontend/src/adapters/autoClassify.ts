import { getLlmKey } from './llmKey'

const STORAGE_KEY = 'ew.autoClassify'

/** 默认开：识别只是建议，失败静默降级，开着对用户没有副作用。 */
export function getAutoClassify(): boolean {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw === null ? true : raw === '1'
  } catch {
    return true
  }
}

export function setAutoClassify(enabled: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, enabled ? '1' : '0')
  } catch {
    /* 写不进去就用默认值 */
  }
}

export { getLlmKey }
