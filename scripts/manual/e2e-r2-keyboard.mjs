/**
 * ⚠️ 未验证：这个脚本在本机沙箱里一次都没跑通，保留给能启动浏览器的环境。
 *
 * 跑不通的原因（2026-11-21 记录）：
 *   - Edge headless 起不来：crashpad `OpenProcess: 拒绝访问`，进程秒退
 *   - 因此 CDP 端口从未打开过，脚本在「找不到 CDP page target」处超时
 * 想验证 R2 的键盘连录，需要在一台能正常起浏览器的机器上跑它，
 * 或者人工按 10 次键。
 *
 * ---
 * R2 键盘连录的端到端测试：真实 Chromium（Edge headless）+ CDP 派发真键。
 *
 * 复现的问题：选完图后焦点留在 <input type="file">，导致 1/W/Enter 被守卫吞掉，
 * 且 Enter 会触发浏览器默认的「再开一次文件选择框」。
 *
 * 用法（前端 5173 + 后端 8000 已启动）：
 *   node scripts/e2e-r2-keyboard.mjs
 *
 * 断言：
 *   1. 选 10 张图后焦点不在 file input 上
 *   2. 全程只按键 10×(1, W, Enter)，衣橱 +10，不多不少
 *   3. 期间一次文件选择框都没弹出
 *   4. 结束文案为「本次已录入 10 件」
 */

import { spawn } from 'node:child_process'
import path from 'node:path'
import process from 'node:process'
import { setTimeout as sleep } from 'node:timers/promises'

const EDGE =
  process.env.EW_BROWSER || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const PORT = Number(process.env.EW_CDP_PORT || 9222)
const APP = process.env.EW_APP_URL || 'http://127.0.0.1:5173'
const ROOT = process.cwd()
const PROFILE = path.join(ROOT, '.tmp', `edge-profile-${Date.now()}`)
const FILES = Array.from({ length: 10 }, (_, i) => path.join(ROOT, '.tmp', 'e2e', `kv-${i + 1}.jpg`))

const log = (...args) => console.log('[e2e]', ...args)

const edge = spawn(
  EDGE,
  [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--mute-audio',
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${PROFILE}`,
    '--window-size=900,1400',
    'about:blank',
  ],
  { stdio: 'ignore' },
)

function cleanup() {
  try {
    edge.kill()
  } catch {
    /* ignore */
  }
}
process.on('exit', cleanup)

class Cdp {
  constructor(url) {
    this.url = url
    this.seq = 0
    this.pending = new Map()
    this.handlers = new Map()
  }

  async connect() {
    this.ws = new WebSocket(this.url)
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve
      this.ws.onerror = () => reject(new Error('CDP 连接失败'))
    })
    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.id) {
        const pending = this.pending.get(msg.id)
        if (!pending) return
        this.pending.delete(msg.id)
        if (msg.error) pending.reject(new Error(`${msg.error.message} (${msg.error.code})`))
        else pending.resolve(msg.result)
        return
      }
      for (const handler of this.handlers.get(msg.method) ?? []) handler(msg.params)
    }
  }

  send(method, params = {}) {
    const id = ++this.seq
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
    })
  }

  on(method, handler) {
    const list = this.handlers.get(method) ?? []
    list.push(handler)
    this.handlers.set(method, list)
  }

  async eval(expression) {
    const result = await this.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
    if (result.exceptionDetails) {
      const detail = result.exceptionDetails.exception?.description ?? result.exceptionDetails.text
      throw new Error(`页面内执行失败: ${detail}`)
    }
    return result.result.value
  }
}

async function waitForTarget(timeoutMs = 25000) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/list`)
      const targets = await res.json()
      const page = targets.find((t) => t.type === 'page')
      if (page?.webSocketDebuggerUrl) return page.webSocketDebuggerUrl
    } catch {
      /* 浏览器还没起来 */
    }
    await sleep(200)
  }
  throw new Error('找不到 CDP page target')
}

async function waitFor(fn, label, timeoutMs = 20000) {
  const started = Date.now()
  let last
  while (Date.now() - started < timeoutMs) {
    try {
      last = await fn()
      if (last) return last
    } catch (err) {
      last = err.message
    }
    await sleep(150)
  }
  throw new Error(`等待超时：${label}（最后状态：${JSON.stringify(last)}）`)
}

const KEYS = {
  1: { key: '1', code: 'Digit1', vk: 49, text: '1' },
  w: { key: 'w', code: 'KeyW', vk: 87, text: 'w' },
  Enter: { key: 'Enter', code: 'Enter', vk: 13, text: '' },
}

async function pressKey(cdp, name) {
  const def = KEYS[name]
  const base = {
    key: def.key,
    code: def.code,
    windowsVirtualKeyCode: def.vk,
    nativeVirtualKeyCode: def.vk,
  }
  await cdp.send('Input.dispatchKeyEvent', {
    type: 'keyDown',
    ...base,
    ...(def.text ? { text: def.text, unmodifiedText: def.text } : {}),
  })
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', ...base })
}

async function main() {
  const cdp = new Cdp(await waitForTarget())
  await cdp.connect()
  await cdp.send('Page.enable')
  await cdp.send('Runtime.enable')

  let chooserCount = 0
  cdp.on('Page.fileChooserOpened', () => {
    chooserCount += 1
  })
  await cdp.send('Page.setInterceptFileChooserDialog', { enabled: true })

  await cdp.send('Page.navigate', { url: APP })
  await waitFor(
    () => cdp.eval(`document.readyState === 'complete' && !!document.querySelector('input[type=file]')`),
    '页面加载',
  )
  // 等 React 首帧
  await waitFor(() => cdp.eval(`document.body.innerText.includes('拍一张')`), 'React 渲染')

  const itemTotal = () =>
    cdp.eval(`fetch('/api/items?limit=1').then((r) => r.json()).then((d) => d.total)`)

  const totalBefore = await itemTotal()
  log('起始衣橱件数:', totalBefore)

  const { root } = await cdp.send('DOM.getDocument', { depth: -1 })
  const { nodeId } = await cdp.send('DOM.querySelector', {
    nodeId: root.nodeId,
    selector: 'input[type=file]',
  })
  if (!nodeId) throw new Error('页面上找不到 input[type=file]')

  await cdp.send('DOM.setFileInputFiles', { nodeId, files: FILES })
  await waitFor(() => cdp.eval(`document.body.innerText.includes('待录入 10')`), '10 张进队列')
  log('10 张图已进队列')

  const activeTag = await cdp.eval(`document.activeElement ? document.activeElement.tagName : 'NONE'`)
  const activeType = await cdp.eval(
    `document.activeElement && document.activeElement.tagName === 'INPUT' ? document.activeElement.type : ''`,
  )
  log('选完图后的焦点:', activeTag, activeType)
  if (activeTag === 'INPUT' && activeType === 'file') {
    throw new Error('焦点仍停留在 file input 上，这是本次要修的 bug')
  }

  for (let i = 1; i <= 10; i += 1) {
    await pressKey(cdp, '1')
    await pressKey(cdp, 'w')
    await pressKey(cdp, 'Enter')
    await waitFor(
      async () => (await itemTotal()) === totalBefore + i,
      `第 ${i} 件保存入库（衣橱应为 ${totalBefore + i}）`,
    )
    if (i === 1) {
      const queueLeft = await cdp.eval(
        `/待录入 (\\d+)/.exec(document.body.innerText)?.[1] ?? '0'`,
      )
      log('第 1 件保存后剩余队列:', queueLeft)
      if (queueLeft !== '9') throw new Error(`队列应剩 9，实际 ${queueLeft}`)
    }
  }

  const totalAfter = await itemTotal()
  const bodyText = await cdp.eval(`document.body.innerText`)
  const queueEmpty = bodyText.includes('本次已录入 10 件')

  log('结束衣橱件数:', totalAfter, '文件框弹出次数:', chooserCount, '收尾文案:', queueEmpty)

  const problems = []
  if (totalAfter - totalBefore !== 10) problems.push(`应 +10，实际 +${totalAfter - totalBefore}`)
  if (chooserCount !== 0) problems.push(`文件选择框弹了 ${chooserCount} 次`)
  if (!queueEmpty) problems.push('队列没有走完（未见「本次已录入 10 件」）')

  if (problems.length > 0) {
    console.error('R2 键盘连录 失败：')
    for (const problem of problems) console.error(' -', problem)
    process.exitCode = 1
    return
  }

  console.log('R2 KEYBOARD E2E PASS：10 件全程只用键盘，无文件框弹出，无重复保存')
}

main()
  .catch((err) => {
    console.error('R2 键盘连录 出错：', err.message)
    process.exitCode = 1
  })
  .finally(() => {
    cleanup()
  })
