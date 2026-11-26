import { useEffect, useState } from 'react'
import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react'

type Block = { type: 'paragraph'; style: string; text: string } | { type: 'table'; rows: string[][] } | { type: 'sheet'; title: string; rows: string[][] }
type LiveDocument = { title: string; revision_id: string; blocks: Block[]; fetched_at: string }
type Snapshot = { text: string; fetched_at: string; revision_id: string }

export default function GoogleBlock({ node, editor, deleteNode, articleId }: NodeViewProps & { articleId: string }) {
  const fileId = String(node.attrs.fileId || '')
  const kind = node.type.name
  const snapshot = node.attrs.snapshot as Snapshot | null
  const [document, setDocument] = useState<LiveDocument | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    if (snapshot) return
    let active = true
    const resource = kind === 'google_spreadsheet' ? 'spreadsheets' : 'documents'
    fetch(`/education-next/api/google/articles/${articleId}/${resource}/${encodeURIComponent(fileId)}`, { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error('Не удалось получить актуальное содержимое из Google. Попробуйте позже.')
        return response.json() as Promise<LiveDocument>
      })
      .then(value => { if (active) { setDocument(value); setError('') } })
      .catch(cause => { if (active) setError((cause as Error).message) })
    return () => { active = false }
  }, [articleId, fileId, kind, retry, snapshot])

  const sourceUrl = String(node.attrs.sourceUrl || '')
  const safeSource = /^https:\/\/docs\.google\.com\/(?:document|spreadsheets)\/d\/[A-Za-z0-9_-]+\/edit$/.test(sourceUrl)
  return <NodeViewWrapper className="google-embed" contentEditable={false}>
    <div className="media-embed-head"><strong>{document?.title || (kind === 'google_spreadsheet' ? 'Google Таблица' : 'Google Документ')}</strong><div className="course-actions">{editor.isEditable && safeSource && <a href={sourceUrl} target="_blank" rel="noopener noreferrer">Редактировать в Google</a>}{editor.isEditable && <button type="button" onClick={deleteNode}>Удалить</button>}</div></div>
    {snapshot ? <div className="google-document-text"><p>Снимок от {new Date(snapshot.fetched_at).toLocaleString('ru-RU')}</p><pre>{snapshot.text}</pre></div>
      : error ? <p role="alert">{error} <button type="button" onClick={() => setRetry(value => value + 1)}>Повторить</button></p>
      : !document ? <p>Загружаем актуальный документ…</p>
      : <div className="google-document-text">{document.blocks.map((block, index) => block.type === 'table' || block.type === 'sheet'
        ? <div key={index}>{block.type === 'sheet' && <h3>{block.title}</h3>}<table><tbody>{block.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>
        : /^HEADING_[1-3]$/.test(block.style) ? <h3 key={index}>{block.text}</h3>
        : <p key={index}>{block.text}</p>)}</div>}
  </NodeViewWrapper>
}
