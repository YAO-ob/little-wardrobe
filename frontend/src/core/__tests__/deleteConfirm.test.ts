// @vitest-environment jsdom
/**
 * 图库删除的二次确认状态机。
 * 覆盖：第一次点只上膛不删、第二次点同一张才删、点别的卡会切过去。
 */

import { describe, expect, it } from 'vitest'
import { resolveDeleteClick } from '../deleteConfirm'

describe('resolveDeleteClick', () => {
  it('没有待确认时，第一次点击只上膛', () => {
    expect(resolveDeleteClick(null, 7)).toEqual({ type: 'arm', id: 7 })
  })

  it('同一张卡再点一次才真删', () => {
    expect(resolveDeleteClick(7, 7)).toEqual({ type: 'delete', id: 7 })
  })

  it('点另一张卡：切成那张卡上膛，不动原来那张', () => {
    expect(resolveDeleteClick(7, 9)).toEqual({ type: 'arm', id: 9 })
  })

  it('连续两次点击走完「上膛 → 删除」', () => {
    const armed = resolveDeleteClick(null, 3)
    const next = resolveDeleteClick(armed.type === 'arm' ? armed.id : null, 3)
    expect(next).toEqual({ type: 'delete', id: 3 })
  })
})
