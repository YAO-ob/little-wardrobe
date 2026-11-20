/** 本地文件 → 可显示的预览地址。用完记得 releasePreview。 */
export function createPreview(file: File): string {
  return URL.createObjectURL(file)
}

export function releasePreview(url: string | null | undefined): void {
  if (url) URL.revokeObjectURL(url)
}
