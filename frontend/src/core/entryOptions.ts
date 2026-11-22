/** W20：录入入口的纯配置——三个纵向小框的顺序、标签、图标。
 *
 * UI 层（CapturePage 的 EntryBoxes）按这个数组渲染。抽成纯数据是为了可测试：
 * 当前前端测试环境（jsdom + vitest，无 @testing-library）无法可靠地提交 React 19
 * createRoot 的渲染（连 <div> 都不会在 act 内同步落 DOM），所以「三小框」靠这份
 * 配置的纯逻辑测试覆盖，真实 DOM 渲染与点击走人工验收。
 */

export type EntryKey = 'camera' | 'album' | 'text'

export interface EntryBoxMeta {
  key: EntryKey
  label: string
  icon: string
}

export const ENTRY_BOXES: EntryBoxMeta[] = [
  { key: 'camera', label: '现在拍', icon: '📷' },
  { key: 'album', label: '从相册选', icon: '🖼' },
  { key: 'text', label: '先描述', icon: '✍️' },
]
