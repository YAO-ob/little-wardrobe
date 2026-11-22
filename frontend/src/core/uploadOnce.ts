/**
 * 保存时决定用哪张已上传的图。
 *
 * 背景（竞态）：选图后立刻按 Enter，流水线正在上传，此时若 save 自己再传一次，
 * 先传完的那张就没人认领，会永久留在 media/tmp。所以：
 *   已有 imageId → 直接用
 *   有在途上传   → 等它，不重复上传
 *   都没有       → 才自己传（uploadedNow=true，失败时需要回收）
 */
export interface ResolvedUpload {
  id: number
  uploadedNow: boolean
}

export async function resolveImageId(
  current: number | null,
  pending: Promise<number | null> | null,
  upload: () => Promise<number>,
): Promise<ResolvedUpload> {
  if (current !== null) return { id: current, uploadedNow: false }

  if (pending) {
    const id = await pending
    if (id !== null) return { id, uploadedNow: false }
  }

  return { id: await upload(), uploadedNow: true }
}
