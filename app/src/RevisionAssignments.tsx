import { useEffect, useState } from 'react'
import CampaignWizard, { type Campaign } from './CampaignWizard'

type Revision = { id: string; article_title: string; number: number; date: string }
const api = '/education-next/api'

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${api}${path}`, { credentials: 'include' })
  if (!response.ok) throw new Error(`Не удалось загрузить редакции (${response.status}).`)
  return response.json() as Promise<T>
}

export default function RevisionAssignments() {
  const [revisions, setRevisions] = useState<Revision[]>([])
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [selectedRevision, setSelectedRevision] = useState<Revision | null>(null)
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([get<Revision[]>('/admin/revisions/assignable'),
      get<Campaign[]>('/admin/campaigns?target_type=article_revision&limit=100')])
      .then(([revisionRows, campaignRows]) => { setRevisions(revisionRows); setCampaigns(campaignRows) })
      .catch(e => setError((e as Error).message))
  }, [])

  function closeCampaign() {
    setSelectedRevision(null); setSelectedCampaign(null)
    get<Campaign[]>('/admin/campaigns?target_type=article_revision&limit=100')
      .then(setCampaigns).catch(e => setError((e as Error).message))
  }

  if (selectedRevision) return <CampaignWizard key={selectedCampaign?.id ?? selectedRevision.id}
    targetType="article_revision" targetId={selectedRevision.id}
    targetTitle={`${selectedRevision.article_title} · редакция № ${selectedRevision.number}`}
    initialCampaign={selectedCampaign} onBack={closeCampaign} />
  return <>
    <div className="crumb">Рабочее пространство / Управление редакциями</div>
    <div className="heading"><div><h1>Редакции статей</h1><p>Выберите выпущенную редакцию, чтобы назначить обновление сотрудникам.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="table"><table><thead><tr><th>Статья</th><th>Редакция</th><th>Дата</th><th>Назначение</th></tr></thead><tbody>
      {revisions.map(revision => <tr key={revision.id}><td>{revision.article_title}</td><td>№ {revision.number}</td>
        <td>{new Date(`${revision.date}T00:00:00`).toLocaleDateString('ru-RU')}</td><td><button onClick={() => setSelectedRevision(revision)}>Назначить</button>
          {campaigns.filter(campaign => campaign.target_id === revision.id).map(campaign => <button key={campaign.id}
            onClick={() => { setSelectedRevision(revision); setSelectedCampaign(campaign) }}>
            {campaign.status === 'active' ? 'Активна' : 'Черновик'} · {campaign.recipient_count}</button>)}</td></tr>)}
    </tbody></table>{revisions.length === 0 && <div className="empty">Выпущенных редакций пока нет.</div>}</div>
  </>
}
