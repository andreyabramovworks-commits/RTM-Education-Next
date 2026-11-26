import { useEffect, useState } from 'react'
import { ArticleView, type Article } from './KnowledgePanel'
import TestAttemptPanel from './TestAttemptPanel'

type Assignment = { id: string; title: string; target_type: string; status: string; due_at: string | null; is_overdue: boolean }
type LearningItem = { id: string; kind: string; title: string; required: boolean; completed: boolean; locked: boolean; test_id: string | null; article: { id: string; summary: string; body: Record<string, unknown> } | null }
type CourseDetail = { id: string; title: string; status: string; target_type: 'course'; due_at: string | null; required_total: number; required_done: number; course: { title: string; description: string; mode: string; sections: { id: string; title: string; items: LearningItem[] }[] } }
type RevisionDetail = { id: string; title: string; status: string; target_type: 'article_revision'; due_at: string | null; revision: { id: string; article_title: string; number: number; date: string; description: string; body: Record<string, unknown>; acknowledged: boolean; test_id: string | null } }
type StandaloneArticleDetail = { id: string; title: string; status: string; target_type: 'course_article'; due_at: string | null; article: { id: string; title: string; summary: string; body: Record<string, unknown> } }
type StandaloneTestDetail = { id: string; title: string; status: string; target_type: 'course_test'; due_at: string | null; test: { id: string; title: string } }
type Detail = CourseDetail | RevisionDetail | StandaloneArticleDetail | StandaloneTestDetail
const api = '/education-next/api'
const statusNames: Record<string, string> = { not_started: 'Не приступил', in_progress: 'В процессе', pending_review: 'Ожидает проверки', returned: 'Возвращено', completed: 'Завершено', exempted: 'Освобождён', cancelled: 'Отменено' }

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${api}${path}`, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) throw new Error(response.status === 409 ? 'Действие сейчас недоступно. Обновите назначение.' : `Не удалось загрузить обучение (${response.status}).`)
  return response.json() as Promise<T>
}

export default function LearningPanel({ tab, onTabChange }: { tab: 'courses' | 'updates'; onTabChange: (tab: 'courses' | 'updates') => void }) {
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [detail, setDetail] = useState<Detail | null>(null)
  const [itemId, setItemId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const selectedItem = detail?.target_type === 'course' ? detail.course.sections.flatMap(section => section.items).find(item => item.id === itemId) : null

  useEffect(() => {
    let active = true
    request<Assignment[]>('/my/assignments').then(rows => { if (active) setAssignments(rows) })
      .catch(e => { if (active) setError((e as Error).message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function open(id: string) {
    setError(''); setLoading(true)
    try { setDetail(await request<Detail>(`/my/assignments/${id}`)); setItemId(null) }
    catch (e) { setError((e as Error).message) }
    finally { setLoading(false) }
  }

  async function action(path: string) {
    if (!detail) return
    setBusy(true); setError('')
    try { await request(path, { method: 'POST' }); await open(detail.id) }
    catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  const filtered = assignments.filter(row => tab === 'courses'
    ? ['course', 'course_article', 'course_test'].includes(row.target_type)
    : row.target_type === 'article_revision')
  return <>
    <div className="crumb">Обучение {detail ? `/ ${detail.title}` : ''}</div>
    <div className="heading"><div><h1>{detail ? detail.title : 'Обучение'}</h1><p>{detail ? statusNames[detail.status] : 'Ваши назначенные курсы и обновления.'}</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {detail ? <>
      <button className="back" onClick={() => { setDetail(null); setItemId(null); request<Assignment[]>('/my/assignments').then(setAssignments).catch(e => setError((e as Error).message)) }}>← К обучению</button>
      {detail.due_at && <p className="learning-due">Срок: {new Date(detail.due_at).toLocaleString('ru-RU')}</p>}
      {detail.status === 'not_started' && <button className="primary" disabled={busy} onClick={() => action(`/my/assignments/${detail.id}/start`)}>Начать обучение</button>}
      {detail.target_type === 'course' && <>
        <p className="learning-progress">Обязательных материалов: {detail.required_done} из {detail.required_total}</p>
        {selectedItem?.article ? <><button className="back" onClick={() => setItemId(null)}>← К программе</button><ArticleView key={selectedItem.id} article={{ id: selectedItem.article.id, title: selectedItem.title, summary: selectedItem.article.summary, body: selectedItem.article.body, row_version: 1 } as Article} editable={false} onSave={async () => {}} />{!selectedItem.completed && detail.status === 'in_progress' && <button className="primary" disabled={busy} onClick={() => action(`/my/assignments/${detail.id}/items/${selectedItem.id}/acknowledge`)}>Ознакомился</button>}{selectedItem.completed && <p>Материал завершён.</p>}</> : selectedItem?.test_id ? <><button className="back" onClick={() => setItemId(null)}>← К программе</button>{selectedItem.completed ? <p>Тест завершён.</p> : <TestAttemptPanel key={selectedItem.id} assignmentId={detail.id} itemId={selectedItem.id} title={selectedItem.title} onDone={() => open(detail.id)} />}</> : <div className="learning-sections">{detail.course.sections.map(section => <section className="panel" key={section.id}><h2>{section.title}</h2>{section.items.map(item => <button className="learning-item" key={item.id} disabled={item.locked || (!item.article && !item.test_id)} onClick={() => setItemId(item.id)}><span>{item.kind === 'article' ? 'Статья' : 'Тест'}</span><b>{item.title}</b><small>{item.completed ? 'Завершено' : item.locked ? 'Пока недоступно' : item.required ? 'Обязательно' : 'Необязательно'}</small></button>)}{section.items.length === 0 && <p>В разделе пока нет материалов.</p>}</section>)}</div>}
      </>}
      {detail.target_type === 'article_revision' && <div className="learning-revision"><p>Редакция № {detail.revision.number} от {new Date(`${detail.revision.date}T00:00:00`).toLocaleDateString('ru-RU')}</p><p>{detail.revision.description}</p><ArticleView key={detail.revision.id} article={{ id: detail.revision.id, title: detail.revision.article_title, summary: '', body: detail.revision.body, row_version: 1 } as Article} editable={false} onSave={async () => {}} />{!detail.revision.acknowledged && detail.status === 'in_progress' && <button className="primary" disabled={busy} onClick={() => action(`/my/assignments/${detail.id}/revision/acknowledge`)}>Ознакомился</button>}{detail.revision.acknowledged && (detail.revision.test_id ? detail.status === 'completed' ? <p>Обновление и тест завершены.</p> : <TestAttemptPanel key={detail.revision.test_id} assignmentId={detail.id} title={`Тест редакции № ${detail.revision.number}`} onDone={() => open(detail.id)} /> : <p>Обновление подтверждено.</p>)}</div>}
      {detail.target_type === 'course_article' && <div className="learning-revision"><ArticleView key={detail.article.id} article={{ id: detail.article.id, title: detail.article.title, summary: detail.article.summary, body: detail.article.body, row_version: 1 } as Article} editable={false} onSave={async () => {}} />{detail.status === 'in_progress' && <button className="primary" disabled={busy} onClick={() => action(`/my/assignments/${detail.id}/article/acknowledge`)}>Ознакомился</button>}{detail.status === 'completed' && <p>Статья завершена.</p>}</div>}
      {detail.target_type === 'course_test' && <div className="learning-revision">{detail.status === 'completed' ? <p>Тест завершён.</p> : <TestAttemptPanel key={detail.test.id} assignmentId={detail.id} standaloneTest title={detail.test.title} onDone={() => open(detail.id)} />}</div>}
    </> : <><div className="tabs"><button className={tab === 'courses' ? 'active' : ''} onClick={() => onTabChange('courses')}>Курсы</button><button className={tab === 'updates' ? 'active' : ''} onClick={() => onTabChange('updates')}>Обновления</button></div>{loading ? <p role="status">Загружаем назначения…</p> : <div className="table"><table><thead><tr><th>Название</th><th>Статус</th><th>Срок</th></tr></thead><tbody>{filtered.map(row => <tr key={row.id} tabIndex={0} onClick={() => open(row.id)} onKeyDown={e => e.key === 'Enter' && open(row.id)}><td><b>{row.title}</b></td><td>{statusNames[row.status] ?? row.status}</td><td>{row.due_at ? new Date(row.due_at).toLocaleDateString('ru-RU') : 'Без срока'}{row.is_overdue && <strong> · Просрочено</strong>}</td></tr>)}</tbody></table>{filtered.length === 0 && <div className="empty">{tab === 'courses' ? 'Назначенных курсов пока нет.' : 'Назначенных обновлений пока нет.'}</div>}</div>}</>}
  </>
}
