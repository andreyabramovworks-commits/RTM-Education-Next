import { useEffect, useState } from 'react'

type CourseSummary = { id: string; title: string; description: string }
type CourseItem = { id: string; kind: 'article' | 'test'; article_id: string | null; test_id: string | null; title: string }
type SourceCourse = CourseSummary & { sections: { id: string; title: string; items: CourseItem[] }[] }
type MaterialPreview = { title: string; summary?: string; body?: unknown;
  questions?: { kind: 'single' | 'multiple' | 'free_text'; prompt: string }[] }

type Props = {
  targetCourseId: string
  targetSectionId: string
  targetSectionTitle: string
  rowVersion: number
  onCopied: () => Promise<void>
  onClose: () => void
}

const api = '/education-next/api'

async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${api}${path}`, { credentials: 'include', signal })
  if (!response.ok) throw new Error(`Не удалось загрузить данные (${response.status}).`)
  return response.json() as Promise<T>
}

function articleText(value: unknown): string {
  if (!value || typeof value !== 'object') return ''
  if (Array.isArray(value)) return value.map(articleText).filter(Boolean).join(' ')
  const node = value as Record<string, unknown>
  return [typeof node.text === 'string' ? node.text : '', articleText(node.content)].filter(Boolean).join(' ')
}

export default function CopyMaterialDialog({ targetCourseId, targetSectionId, targetSectionTitle,
  rowVersion, onCopied, onClose }: Props) {
  const [search, setSearch] = useState('')
  const [courses, setCourses] = useState<CourseSummary[]>([])
  const [sourceCourse, setSourceCourse] = useState<SourceCourse | null>(null)
  const [sourceItem, setSourceItem] = useState<CourseItem | null>(null)
  const [preview, setPreview] = useState<MaterialPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [copying, setCopying] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const timeout = setTimeout(() => {
      read<CourseSummary[]>(`/admin/courses?search=${encodeURIComponent(search)}&limit=100`, controller.signal)
        .then(rows => setCourses(rows.filter(row => row.id !== targetCourseId)))
        .catch(reason => { if (!controller.signal.aborted) setError((reason as Error).message) })
    }, 250)
    return () => { clearTimeout(timeout); controller.abort() }
  }, [search, targetCourseId])

  async function selectCourse(id: string) {
    setLoading(true); setError(''); setSourceItem(null); setPreview(null)
    try { setSourceCourse(await read<SourceCourse>(`/admin/courses/${id}`)) }
    catch (reason) { setError((reason as Error).message) }
    finally { setLoading(false) }
  }

  async function selectItem(item: CourseItem) {
    const id = item.kind === 'article' ? item.article_id : item.test_id
    if (!sourceCourse || !id) return
    setLoading(true); setError(''); setSourceItem(item); setPreview(null)
    try {
      const path = item.kind === 'article'
        ? `/admin/courses/${sourceCourse.id}/articles/${id}` : `/admin/tests/${id}`
      setPreview(await read<MaterialPreview>(path))
    } catch (reason) { setError((reason as Error).message) }
    finally { setLoading(false) }
  }

  async function copy() {
    if (!sourceItem || !preview || copying) return
    setCopying(true); setError('')
    try {
      const response = await fetch(`${api}/admin/courses/${targetCourseId}/sections/${targetSectionId}/copy-item`, {
        method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_item_id: sourceItem.id, row_version: rowVersion }),
      })
      if (response.status === 409) throw new Error('Курс изменился. Закройте окно и обновите курс перед копированием.')
      if (!response.ok) throw new Error(`Не удалось создать копию (${response.status}).`)
      await onCopied()
    } catch (reason) { setError((reason as Error).message) }
    finally { setCopying(false) }
  }

  return <div className="copy-dialog-overlay">
    <div className="copy-dialog" role="dialog" aria-modal="true" aria-labelledby="copy-dialog-title">
      <div className="copy-dialog-head"><div><small>Программа / {targetSectionTitle}</small><h2 id="copy-dialog-title">Копировать из другого курса</h2></div><button type="button" onClick={onClose} disabled={copying} aria-label="Закрыть выбор материала">×</button></div>
      <p>Выберите сохранённую статью или тест. Копия получит собственное содержание и не перенесёт назначения или результаты.</p>
      <label>Поиск исходного курса<input autoFocus value={search} onChange={event => setSearch(event.target.value)} placeholder="Название курса" /></label>
      <div className="copy-dialog-columns">
        <div><h3>Курсы</h3><div className="copy-dialog-list">{courses.map(row => <button type="button" className={sourceCourse?.id === row.id ? 'chosen' : ''} key={row.id} onClick={() => void selectCourse(row.id)} disabled={copying}>{row.title}</button>)}{courses.length === 0 && <p>Другие курсы не найдены.</p>}</div></div>
        <div><h3>Материалы</h3><div className="copy-dialog-list">{sourceCourse?.sections.flatMap(section => section.items.map(item => <button type="button" className={sourceItem?.id === item.id ? 'chosen' : ''} key={item.id} onClick={() => void selectItem(item)} disabled={copying}><small>{section.title} · {item.kind === 'article' ? 'Статья' : 'Тест'}</small>{item.title}</button>))}{!sourceCourse && <p>Сначала выберите курс.</p>}{sourceCourse && !sourceCourse.sections.some(section => section.items.length) && <p>В этом курсе нет материалов.</p>}</div></div>
      </div>
      {loading && <p role="status">Загружаем…</p>}
      {preview && <section className="copy-dialog-preview"><small>Предпросмотр источника</small><h3>{preview.title}</h3>{preview.summary && <p>{preview.summary}</p>}{sourceItem?.kind === 'article' && <p>{articleText(preview.body).slice(0, 700) || 'В статье пока нет собственного текста.'}</p>}{sourceItem?.kind === 'test' && <><p>Вопросов: {preview.questions?.length ?? 0}</p><ol>{preview.questions?.map((question, index) => <li key={index}><span>{question.kind === 'free_text' ? 'Свободный ответ' : question.kind === 'multiple' ? 'Несколько вариантов' : 'Один вариант'}</span><p>{question.prompt}</p></li>)}</ol></>}</section>}
      {error && <p role="alert" className="error">{error}</p>}
      <div className="copy-dialog-actions"><button type="button" onClick={onClose} disabled={copying}>Отмена</button><button type="button" className="primary" onClick={() => void copy()} disabled={!sourceItem || !preview || loading || copying}>{copying ? 'Создаём копию…' : 'Создать копию'}</button></div>
    </div>
  </div>
}
