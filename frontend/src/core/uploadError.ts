/** 上传失败时的用户可读文案：纯函数，方便单测。 */

export const IPHONE_FORMAT_HINT =
  '不支持这个格式。iPhone 请在 设置 → 相机 → 格式 里选「兼容性最佳」，或改用相册里的 JPEG 照片'

export function uploadErrorMessage(status: number, detail: string): string {
  if (status === 415 && detail.includes('格式')) return IPHONE_FORMAT_HINT
  if (status === 413) return '图片太大，请压缩到 12MB 以内'
  return detail
}
