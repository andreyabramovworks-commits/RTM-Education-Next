import { useEffect, useState } from 'react'
import CampaignWizard, { type Campaign } from './CampaignWizard'
import TestEditor from './TestEditor'

type Article = { id: string; title: string; summary: string; row_version: number }
type Revision = { id: string; number: number; date: string; description: string; published_at: string; completion_mode: 'acknowledge' | 'full_test'; test_id: string | null }
const api = '/education-next/api'

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

export default function RevisionPanel() {
  const [articles, setArticles] = useState<Article[]>([])
  const [articleId, setArticleId] = useState('')
  const [revisions, setRevisions] = useState<Revision[]>([])
  const [date, setDate] = useState('')
  const [description, setDescription] = useState('')
  const [completionMode, setCompletionMode] = useState<'acknowledge' | 'full_test'>('acknowledge')
  const [copyTestId, setCopyTestId] = useState('')
  const [editingTestId, setEditingTestId] = useState<string | null>(null)
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

  return <>
    {editingTestId ? <TestEditor testId={editingTestId} backLabel="К редакциям" onBack={() => setEditingTestId(null)} /> : campaignRevisionId && article ? <CampaignWizard key={selectedCampaign?.id ?? campaignRevisionId} targetType="article_revision" targetId={campaignRevisionId} targetTitle={`${article.title} · редакция № ${revisions.find(row => row.id === campaignRevisionId)?.number ?? ''}`} initialCampaign={selectedCampaign} onBack={closeCampaign} /> : <>
    <div className="crumb">Рабочее пространство / Управление редакциями</div>
    <div className="heading"><div><h1>Управление редакциями</h1><p>Редакция фиксирует содержание статьи Базы знаний. Кампания запускается отдельно.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="revision-layout"><div className="panel"><h2>Статьи</h2>{articles.map(row => <button key={row.id} className={`revision-article ${row.id === articleId ? 'selected' : ''}`} onClick={() => setArticleId(row.id)}>{row.title}</button>)}{articles.length === 0 && <p>Статей пока нет.</p>}</div>
      <div>{article ? <><div className="panel"><h2>{article.title}</h2><p>{article.summary || 'Описание не добавлено.'}</p><div className="revision-form"><label>Дата редакции<input type="date" value={date} onChange={e => setDate(e.target.value)} /></label><label>Что изменилось<textarea value={description} onChange={e => setDescription(e.target.value)} /></label><label><input type="radio" checked={completionMode === 'acknowledge'} onChange={() => setCompletionMode('acknowledge')} /> Подтверждение ознакомления</label><label><input type="radio" checked={completionMode === 'full_test'} onChange={() => setCompletionMode('full_test')} /> Полный тест после чтения</label>{completionMode === 'full_test' && <label>Основа для теста<select value={copyTestId} onChange={e => setCopyTestId(e.target.value)}><option value="">Новый пустой тест</option>{revisions.filter(row => row.test_id).map(row => <option key={row.id} value={row.test_id ?? ''}>Копия теста редакции № {row.number}</option>)}</select></label>}<button className="primary" disabled={saving || !date || !description.trim()} onClick={publish}>{saving ? 'Публикуем…' : 'Выпустить редакцию'}</button></div></div><div className="panel"><h2>История редакций</h2>{revisions.map(row => <div className="revision-row" key={row.id}><b>№ {row.number} · {new Date(`${row.date}T00:00:00`).toLocaleDateString('ru-RU')}</b><span>{row.description}</span><span>{row.test_id ? 'Полный тест' : 'Подтверждение ознакомления'}</span>{row.test_id && <button onClick={() => setEditingTestId(row.test_id)}>Открыть тест</button>}<button onClick={() => { setCampaignRevisionId(row.id); setSelectedCampaign(null) }}>Назначить обновление</button>{campaigns.filter(campaign => campaign.target_id === row.id).map(campaign => <button key={campaign.id} onClick={() => { setCampaignRevisionId(row.id); setSelectedCampaign(campaign) }}>Кампания: {campaign.status === 'active' ? 'активна' : 'черновик'} · {campaign.recipient_count}</button>)}</div>)}{revisions.length === 0 && <p>Редакций пока нет.</p>}</div></> : <div className="empty">Выберите статью для просмотра редакций.</div>}</div>
    </div>
    </>}
  </>
}
