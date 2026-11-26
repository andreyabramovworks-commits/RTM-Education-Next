import { useEffect, useState } from 'react'
import CampaignWizard, { type Campaign } from './CampaignWizard'
import TestEditor from './TestEditor'
import { ArticleView, type Article as KnowledgeArticle } from './KnowledgePanel'

type Article = { id: string; title: string; summary: string; row_version: number }
type Revision = { id: string; number: number; date: string; description: string; published_at: string; completion_mode: 'acknowledge' | 'full_test'; test_id: string | null; deleted_at?: string | null; delete_reason?: string | null }
type RevisionSnapshot = { id: string; article_id: string; number: number; date: string; description: string; body: Record<string, unknown> }
const api = '/education-next/api'

function snapshotText(value: unknown): string {
  if (Array.isArray(value)) return value.map(snapshotText).join(' ')
  if (!value || typeof value !== 'object') return ''
  const node = value as Record<string, unknown>
  return [typeof node.text === 'string' ? node.text : '',
    node.attrs && typeof node.attrs === 'object' && typeof (node.attrs as Record<string, unknown>).snapshot === 'object'
      ? String(((node.attrs as Record<string, unknown>).snapshot as Record<string, unknown>)?.text ?? '') : '',
    snapshotText(node.content)].filter(Boolean).join(' ')
}

async function read<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${api}${path}`, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) {
    if (response.status === 409) {
      const detail = (await response.json() as { detail?: string }).detail
      throw new Error(detail === 'Google document snapshot is unavailable'
        ? 'Не удалось получить актуальный снимок Google Docs. Редакция не выпущена.'
        : 'Статья изменилась или редакция с этой датой уже есть. Обновите раздел.')
    }
    throw new Error(`Не удалось выполнить действие (${response.status}).`)
  }
  return response.json() as Promise<T>
}

export default function RevisionPanel({ canWithdraw = false }: { canWithdraw?: boolean }) {
  const [articles, setArticles] = useState<Article[]>([])
  const [articleId, setArticleId] = useState('')
  const [revisions, setRevisions] = useState<Revision[]>([])
  const [date, setDate] = useState('')
  const [description, setDescription] = useState('')
  const [completionMode, setCompletionMode] = useState<'acknowledge' | 'full_test'>('acknowledge')
  const [copyTestId, setCopyTestId] = useState('')
  const [editingTestId, setEditingTestId] = useState<string | null>(null)
  const [viewingRevision, setViewingRevision] = useState<RevisionSnapshot | null>(null)
  const [revisionSearch, setRevisionSearch] = useState('')
  const [campaignRevisionId, setCampaignRevisionId] = useState<string | null>(null)
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const article = articles.find(row => row.id === articleId)

  useEffect(() => { read<{ articles: Article[] }>('/admin/knowledge').then(data => setArticles(data.articles)).catch(e => setError((e as Error).message)) }, [])
  useEffect(() => {
    if (!articleId) return
    read<Revision[]>(`/admin/knowledge/articles/${articleId}/revisions`).then(setRevisions).catch(e => setError((e as Error).message))
  }, [articleId])
  useEffect(() => {
    read<Campaign[]>('/admin/campaigns?target_type=article_revision')
      .then(setCampaigns).catch(e => setError((e as Error).message))
  }, [])

  function closeCampaign() {
    setCampaignRevisionId(null); setSelectedCampaign(null)
    read<Campaign[]>('/admin/campaigns?target_type=article_revision')
      .then(setCampaigns).catch(e => setError((e as Error).message))
  }

  async function openRevision(id: string) {
    setError('')
    try { setViewingRevision(await read<RevisionSnapshot>(`/knowledge/revisions/${id}`)); setRevisionSearch('') }
    catch (e) { setError((e as Error).message) }
  }

  async function publish() {
    if (!article || !date || !description.trim()) return
    if (!window.confirm(`Выпустить редакцию статьи «${article.title}» от ${date}? Назначения при этом не создаются.`)) return
    setSaving(true); setError('')
    try {
      const revision = await read<Revision>(`/admin/knowledge/articles/${article.id}/revisions`, {
        method: 'POST', body: JSON.stringify({ revision_date: date, description: description.trim(),
          row_version: article.row_version, completion_mode: completionMode,
          copy_test_id: completionMode === 'full_test' && copyTestId ? copyTestId : null }),
      })
      setRevisions(rows => [revision, ...rows]); setDescription('')
      if (revision.test_id) setEditingTestId(revision.test_id)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }

  async function withdraw(revision: Revision) {
    if (!article || revision.deleted_at) return
    const reason = window.prompt(`Причина удаления редакции № ${revision.number}. Назначения и результаты сохранятся.`)?.trim()
    if (!reason) return
    if (!window.confirm(`Удалить редакцию № ${revision.number} статьи «${article.title}»? Новые назначения станут недоступны.`)) return
    setSaving(true); setError('')
    try {
      const result = await read<{ deleted_at: string; delete_reason: string }>(`/admin/knowledge/articles/${article.id}/revisions/${revision.id}/withdraw`, {
        method: 'POST', body: JSON.stringify({ reason, confirmed: true }),
      })
      setRevisions(rows => rows.map(row => row.id === revision.id ? { ...row, ...result } : row))
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }

  return <>
    {editingTestId ? <TestEditor testId={editingTestId} backLabel="К редакциям" onBack={() => setEditingTestId(null)} /> : viewingRevision ? <div className="revision-history-view"><button className="back" onClick={() => setViewingRevision(null)}>← К редакциям</button><div className="heading"><div><h1>{article?.title ?? 'Статья'} · редакция № {viewingRevision.number}</h1><p>{viewingRevision.description}</p></div></div><label>Поиск в сохранённой редакции<input value={revisionSearch} onChange={event => setRevisionSearch(event.target.value)} placeholder="Текст статьи или Google Docs" /></label>{revisionSearch.trim() && <p role="status">{snapshotText(viewingRevision.body).toLocaleLowerCase('ru-RU').includes(revisionSearch.trim().toLocaleLowerCase('ru-RU')) ? 'Найдено в редакции' : 'В редакции не найдено'}</p>}<ArticleView article={{ id: viewingRevision.article_id, title: article?.title ?? 'Статья', summary: '', body: viewingRevision.body, row_version: 1 } as KnowledgeArticle} editable={false} onSave={async () => {}} /></div> : campaignRevisionId && article ? <CampaignWizard key={selectedCampaign?.id ?? campaignRevisionId} targetType="article_revision" targetId={campaignRevisionId} targetTitle={`${article.title} · редакция № ${revisions.find(row => row.id === campaignRevisionId)?.number ?? ''}`} initialCampaign={selectedCampaign} onBack={closeCampaign} /> : <>
    <div className="crumb">Рабочее пространство / Управление редакциями</div>
    <div className="heading"><div><h1>Управление редакциями</h1><p>Редакция фиксирует содержание статьи Базы знаний. Кампания запускается отдельно.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="revision-layout"><div className="panel"><h2>Статьи</h2>{articles.map(row => <button key={row.id} className={`revision-article ${row.id === articleId ? 'selected' : ''}`} onClick={() => setArticleId(row.id)}>{row.title}</button>)}{articles.length === 0 && <p>Статей пока нет.</p>}</div>
      <div>{article ? <><div className="panel"><h2>{article.title}</h2><p>{article.summary || 'Описание не добавлено.'}</p><div className="revision-form"><label>Дата редакции<input type="date" value={date} onChange={e => setDate(e.target.value)} /></label><label>Что изменилось<textarea value={description} onChange={e => setDescription(e.target.value)} /></label><label><input type="radio" checked={completionMode === 'acknowledge'} onChange={() => setCompletionMode('acknowledge')} /> Подтверждение ознакомления</label><label><input type="radio" checked={completionMode === 'full_test'} onChange={() => setCompletionMode('full_test')} /> Полный тест после чтения</label>{completionMode === 'full_test' && <label>Основа для теста<select value={copyTestId} onChange={e => setCopyTestId(e.target.value)}><option value="">Новый пустой тест</option>{revisions.filter(row => row.test_id).map(row => <option key={row.id} value={row.test_id ?? ''}>Копия теста редакции № {row.number}</option>)}</select></label>}<button className="primary" disabled={saving || !date || !description.trim()} onClick={publish}>{saving ? 'Публикуем…' : 'Выпустить редакцию'}</button></div></div><div className="panel"><h2>История редакций</h2>{revisions.map(row => <div className="revision-row" key={row.id}><b>№ {row.number} · {new Date(`${row.date}T00:00:00`).toLocaleDateString('ru-RU')}</b><span>{row.description}</span><span>{row.test_id ? 'Полный тест' : 'Подтверждение ознакомления'}</span>{row.deleted_at && <span>Удалена · {row.delete_reason}</span>}<button onClick={() => void openRevision(row.id)}>Просмотреть редакцию</button>{row.test_id && <button onClick={() => setEditingTestId(row.test_id)}>Открыть тест</button>}{!row.deleted_at && <button onClick={() => { setCampaignRevisionId(row.id); setSelectedCampaign(null) }}>Назначить обновление</button>}{canWithdraw && !row.deleted_at && <button disabled={saving} onClick={() => void withdraw(row)}>Удалить редакцию</button>}{campaigns.filter(campaign => campaign.target_id === row.id).map(campaign => <button key={campaign.id} onClick={() => { setCampaignRevisionId(row.id); setSelectedCampaign(campaign) }}>Кампания: {campaign.status === 'active' ? 'активна' : 'черновик'} · {campaign.recipient_count}</button>)}</div>)}{revisions.length === 0 && <p>Редакций пока нет.</p>}</div></> : <div className="empty">Выберите статью для просмотра редакций.</div>}</div>
    </div>
    </>}
  </>
}
