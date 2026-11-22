// @vitest-environment jsdom
/** 保存时的上传去重：在途上传必须等待，不能双传。 */

import { describe, expect, it, vi } from 'vitest'
import { resolveImageId } from '../uploadOnce'

describe('resolveImageId', () => {
  it('已有 imageId 时不再上传', async () => {
    const upload = vi.fn(async () => 99)

    const result = await resolveImageId(7, null, upload)

    expect(result).toEqual({ id: 7, uploadedNow: false })
    expect(upload).not.toHaveBeenCalled()
  })

  it('有在途上传时等它，不重复上传（竞态防线）', async () => {
    const upload = vi.fn(async () => 99)
    const pending = Promise.resolve(42)

    const result = await resolveImageId(null, pending, upload)

    expect(result).toEqual({ id: 42, uploadedNow: false })
    expect(upload).not.toHaveBeenCalled()
  })

  it('在途上传失败时才自己传，并标记 uploadedNow', async () => {
    const upload = vi.fn(async () => 99)

    const result = await resolveImageId(null, Promise.resolve(null), upload)

    expect(result).toEqual({ id: 99, uploadedNow: true })
    expect(upload).toHaveBeenCalledTimes(1)
  })
})
