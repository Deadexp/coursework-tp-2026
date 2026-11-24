import { useEffect, useState } from 'react'
import { requestBlob } from '../api/client'
import type { Word } from '../api/vocabulary'

export function WordImage({
  word, className = '', width = 96, height = 96,
}: { word: Word; className?: string; width?: number; height?: number }) {
  const [loaded, setLoaded] = useState<{ path: string; url: string } | null>(null)
  const path = word.image_url
  useEffect(() => {
    if (!path?.startsWith('/vocabulary/')) return
    let active = true
    let objectUrl: string | null = null
    requestBlob(path).then((blob) => {
      if (!active) return
      objectUrl = URL.createObjectURL(blob)
      setLoaded({ path, url: objectUrl })
    }).catch(() => { /* A missing illustration must not hide the word. */ })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])
  const url = path?.startsWith('/vocabulary/')
    ? loaded?.path === path ? loaded.url : null
    : path
  return url ? (
    <img src={url} alt={`Иллюстрация: ${word.text}`} width={width} height={height}
      className={className} style={{ objectFit: 'contain', borderRadius: 12 }} />
  ) : null
}
