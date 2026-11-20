import { vi } from 'vitest'

// jsdom 没有这两个 API，预览图相关代码需要它们存在
if (!URL.createObjectURL) {
  URL.createObjectURL = vi.fn(() => 'blob:preview')
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = vi.fn()
}

// React 19 的 act 需要这个标志位
;(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true
