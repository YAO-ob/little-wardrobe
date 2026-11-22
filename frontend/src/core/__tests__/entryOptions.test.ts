/** W20：录入入口配置的纯逻辑——数量、顺序、标签、图标都由这份数据驱动。 */

import { describe, expect, it } from 'vitest'
import { ENTRY_BOXES } from '../entryOptions'

describe('ENTRY_BOXES 录入入口配置', () => {
  it('恰好三个，顺序为 现在拍 / 从相册选 / 先描述', () => {
    expect(ENTRY_BOXES).toHaveLength(3)
    expect(ENTRY_BOXES.map((b) => b.label)).toEqual(['现在拍', '从相册选', '先描述'])
    expect(ENTRY_BOXES.map((b) => b.key)).toEqual(['camera', 'album', 'text'])
  })

  it('key 不重复', () => {
    expect(new Set(ENTRY_BOXES.map((b) => b.key)).size).toBe(ENTRY_BOXES.length)
  })

  it('每个都带非空图标与非空标签', () => {
    for (const b of ENTRY_BOXES) {
      expect(b.icon.length).toBeGreaterThan(0)
      expect(b.label.length).toBeGreaterThan(0)
    }
  })
})
