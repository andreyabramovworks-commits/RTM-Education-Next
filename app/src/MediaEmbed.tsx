import { useEffect, useState } from 'react'
import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react'

type MediaInfo = { id: string; kind: 'video' | 'audio'; source_type: 'upload' | 'rutube'; title: string; file_url: string | null; embed_url: string | null }

export default function MediaBlock({ node, editor, updateAttributes, deleteNode }: NodeViewProps) {
  const assetId = String(node.attrs.assetId || '')
  const [info, setInfo] = useState<MediaInfo | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    fetch(`/education-next/api/media/${assetId}/info`, { credentials: 'include' })
      .then(async response => { if (!response.ok) throw new Error('Материал сейчас недоступен.'); return response.json() as Promise<MediaInfo> })
      .then(value => { if (active) { setInfo(value); setError('') } })
      .catch(e => { if (active) setError((e as Error).message) })
    return () => { active = false }
  }, [assetId, retry])
  return <NodeViewWrapper className="media-embed" contentEditable={false}>
    <div className="media-embed-head"><strong>{info?.title || 'Медиа'}</strong>{editor.isEditable && <button type="button" onClick={deleteNode}>Удалить</button>}</div>
    {error ? <p role="alert">{error} <button type="button" onClick={() => setRetry(value => value + 1)}>Повторить</button></p>
      : !info ? <p>Загружаем материал…</p>
      : info.source_type === 'rutube' && info.embed_url ? <div className="media-video"><iframe title={info.title} src={info.embed_url} allow="autoplay; encrypted-media; fullscreen; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" /></div>
      : info.kind === 'video' && info.file_url ? <video controls preload="metadata" src={info.file_url} />
      : info.file_url ? <audio controls preload="metadata" src={info.file_url} /> : <p>Материал недоступен.</p>}
    {editor.isEditable ? <label>Описание<input value={String(node.attrs.caption || '')} onChange={event => updateAttributes({ caption: event.target.value })} /></label>
      : node.attrs.caption && <p>{String(node.attrs.caption)}</p>}
  </NodeViewWrapper>
}
