/**
 * 衣柜删除按钮的二次确认状态机。
 *
 * 不用 window.confirm：浏览器在「阻止此页面创建更多对话框」被勾选、
 * 或页面处在没有 allow-modals 的 iframe 里时，会静默返回 false，
 * 表现就是「点了没反应」。改成按钮自身两态，不依赖原生对话框。
 */

export type DeleteClickAction =
  | { type: 'arm'; id: number } // 第一次点：进入待确认
  | { type: 'delete'; id: number } // 第二次点同一张：真删

/**
 * @param current 当前处于待确认状态的卡片 id（null 表示没有）
 * @param clickedId 这次点击的卡片 id
 */
export function resolveDeleteClick(current: number | null, clickedId: number): DeleteClickAction {
  return current === clickedId ? { type: 'delete', id: clickedId } : { type: 'arm', id: clickedId }
}
