import type { ItemImage } from '../core/types'

/** 上传一张原图，返回服务端生成的图片记录。 */
export async function uploadImageFile(file: File): Promise<ItemImage> {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch('/api/images', { method: 'POST', body: form })
  if (!res.ok) {
    let detail = `上传失败（${res.status}）`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  return (await res.json()) as ItemImage
}
