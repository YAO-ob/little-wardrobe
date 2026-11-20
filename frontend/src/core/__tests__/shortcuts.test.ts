// @vitest-environment jsdom
/**
 * R2 回归测试：焦点守卫 + 快捷键映射。
 *
 * 线上 bug 的根因就在 isTextEntry：老实现把 tagName === 'INPUT' 全拦掉，
 * file input 也算在内，于是选完图之后 1/W/Enter 全部失效。
 */

import { describe, expect, it } from 'vitest'
import { isTextEntry, resolveShortcut } from '../shortcuts'

function input(type: string): HTMLInputElement {
  const element = document.createElement('input')
  element.type = type
  return element
}

describe('isTextEntry：决定要不要让键盘快捷键让路', () => {
  it('file input 不能拦（R2 的 bug 就出在这里）', () => {
    expect(isTextEntry(input('file'))).toBe(false)
  })

  it('button / checkbox / radio 不能拦', () => {
    expect(isTextEntry(input('button'))).toBe(false)
    expect(isTextEntry(input('checkbox'))).toBe(false)
    expect(isTextEntry(input('radio'))).toBe(false)
  })

  it('按钮元素不能拦', () => {
    expect(isTextEntry(document.createElement('button'))).toBe(false)
  })

  it.each(['text', 'search', 'number', 'password', 'email', 'tel', 'url'])(
    '%s 输入框要拦（用户在打字）',
    (type) => {
      expect(isTextEntry(input(type))).toBe(true)
    },
  )

  it('textarea / select 要拦', () => {
    expect(isTextEntry(document.createElement('textarea'))).toBe(true)
    expect(isTextEntry(document.createElement('select'))).toBe(true)
  })

  it('contentEditable 要拦', () => {
    const element = document.createElement('div')
    // jsdom 的 contentEditable 属性是空实现，直接写属性更贴近真实 DOM
    element.setAttribute('contenteditable', 'true')
    expect(isTextEntry(element)).toBe(true)
  })

  it('普通容器和 window 不拦', () => {
    expect(isTextEntry(document.createElement('div'))).toBe(false)
    expect(isTextEntry(document.body)).toBe(false)
    expect(isTextEntry(null)).toBe(false)
  })
})

describe('resolveShortcut：按键 → 动作', () => {
  it('1-6 映射到六个品类', () => {
    expect(resolveShortcut('1')).toEqual({ type: 'category', value: 'top' })
    expect(resolveShortcut('2')).toEqual({ type: 'category', value: 'outer' })
    expect(resolveShortcut('3')).toEqual({ type: 'category', value: 'bottom' })
    expect(resolveShortcut('4')).toEqual({ type: 'category', value: 'shoes' })
    expect(resolveShortcut('5')).toEqual({ type: 'category', value: 'accessory' })
    expect(resolveShortcut('6')).toEqual({ type: 'category', value: 'dress' })
  })

  it('Q/W/E 映射薄中厚，且大小写都认', () => {
    expect(resolveShortcut('q')).toEqual({ type: 'warmth', value: 1 })
    expect(resolveShortcut('W')).toEqual({ type: 'warmth', value: 2 })
    expect(resolveShortcut('E')).toEqual({ type: 'warmth', value: 3 })
  })

  it('Enter 保存、Backspace 跳过', () => {
    expect(resolveShortcut('Enter')).toEqual({ type: 'save' })
    expect(resolveShortcut('Backspace')).toEqual({ type: 'skip' })
  })

  it('其他键返回 null，交还浏览器', () => {
    expect(resolveShortcut('a')).toBeNull()
    expect(resolveShortcut('7')).toBeNull()
    expect(resolveShortcut('Escape')).toBeNull()
  })
})

describe('bug 现场还原：焦点在 file input 上时按键仍然可用', () => {
  it('目标元素是 file input 时，守卫放行且 1/W/Enter 都能解析出动作', () => {
    const fileInput = input('file')
    expect(isTextEntry(fileInput)).toBe(false)
    expect(resolveShortcut('1')).toEqual({ type: 'category', value: 'top' })
    expect(resolveShortcut('w')).toEqual({ type: 'warmth', value: 2 })
    expect(resolveShortcut('Enter')).toEqual({ type: 'save' })
  })

  it('目标若换成文本框，则不解析（避免抢输入）', () => {
    const textInput = input('text')
    expect(isTextEntry(textInput)).toBe(true)
  })
})
