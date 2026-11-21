// @vitest-environment jsdom
/** 上传错误文案映射：格式问题要给 iPhone 用户可执行的建议。 */

import { describe, expect, it } from 'vitest'
import { IPHONE_FORMAT_HINT, uploadErrorMessage } from '../uploadError'

describe('uploadErrorMessage', () => {
  it('415 且提到格式 → iPhone 设置提示', () => {
    expect(uploadErrorMessage(415, '不支持的格式 .txt，请用 jpg / png / webp')).toBe(
      IPHONE_FORMAT_HINT,
    )
    expect(uploadErrorMessage(415, '图片无法解析，格式可能不受支持')).toBe(IPHONE_FORMAT_HINT)
  })

  it('413 → 压缩提示', () => {
    expect(uploadErrorMessage(413, '图片过大')).toBe('图片太大，请压缩到 12MB 以内')
  })

  it('其他状态原样返回 detail', () => {
    expect(uploadErrorMessage(500, '服务器开小差了')).toBe('服务器开小差了')
    expect(uploadErrorMessage(415, '图片无法解析')).toBe('图片无法解析')
  })
})
