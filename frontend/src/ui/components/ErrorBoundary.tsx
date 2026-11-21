import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * 兜住渲染期异常，避免整页白屏。
 * 注意：事件回调里的异常它抓不到（那类错误不会冒泡到 React 渲染），
 * 但「白屏」绝大多数来自渲染期（比如某个浏览器 API 不存在）。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // 控制台留完整堆栈，页面只给人能看的一小段
    console.error('render error:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    const message = (error.message || String(error)).slice(0, 200)

    return (
      <div className="mx-auto flex min-h-full max-w-xl flex-col items-center justify-center gap-3 px-6 py-16 text-center">
        <p className="text-base font-semibold">页面出错了</p>
        <p className="break-all rounded-xl bg-red-50 px-3 py-2 text-xs leading-5 text-red-700">
          {message}
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-xl bg-black px-4 py-2 text-sm text-white"
        >
          重新加载
        </button>
        <p className="text-[11px] text-black/40">如果反复出现，把上面这段错误信息发给我</p>
      </div>
    )
  }
}
