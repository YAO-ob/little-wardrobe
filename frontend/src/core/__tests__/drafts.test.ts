// @vitest-environment jsdom
/** 草稿追加：空数组不能崩、不能凭空产生卡片。 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { appendDrafts, makeDraftId } from '../drafts'

function makeFile(name: string): File {
  return new File([new Uint8Array([1])], name, { type: 'image/jpeg' })
}

describe('appendDrafts', () => {
  it('空数组返回原数组，不产生 draft', () => {
    const prev = [{ id: 'a' }]
    const next = appendDrafts(prev, [], (file) => ({ id: file.name }))
    expect(next).toBe(prev)
    expect(next).toHaveLength(1)
  })

  it('空队列 + 空数组也不崩', () => {
    const next = appendDrafts<{ id: string }>([], [], (file) => ({ id: file.name }))
    expect(next).toEqual([])
  })

  it('有文件时按顺序追加到末尾', () => {
    const prev = [{ id: 'a' }]
    const next = appendDrafts(prev, [makeFile('1.jpg'), makeFile('2.jpg')], (file) => ({
      id: file.name,
    }))
    expect(next.map((d) => d.id)).toEqual(['a', '1.jpg', '2.jpg'])
  })
})

describe('makeDraftId', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('安全上下文下返回 UUID 形态（36 字符）', () => {
    const id = makeDraftId()
    expect(id).toHaveLength(36)
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)
  })

  it('crypto 存在但没有 randomUUID（http 局域网访问）→ 降级且 100 次不重复', () => {
    vi.stubGlobal('crypto', {})

    const ids = new Set(Array.from({ length: 100 }, () => makeDraftId()))

    expect(ids.size).toBe(100)
    for (const id of ids) expect(id.length).toBeGreaterThan(8)
  })

  it('crypto 完全不存在时也不崩', () => {
    vi.stubGlobal('crypto', undefined)
    expect(makeDraftId().length).toBeGreaterThan(8)
  })
})
