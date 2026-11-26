import { useEffect, useState } from 'react'
import ReviewAssignment from './ReviewAssignment'

type Domain = 'materials' | 'courses'
type Group = 'targets' | 'employees'
type Metrics = { assignments: number; completed: number; not_started: number; in_progress: number;
  pending_review: number; returned: number; exempted: number; overdue: number;
  required_total: number; required_done: number; progress_percent: number }
type Summary = Metrics & { employees: number }
type CampaignRow = Metrics & { campaign_id: string; campaign_title: string;
  launched_at: string | null; campaign_due_at: string | null; completion_percent: number }
type TargetRow = Metrics & { target_type: string; campaign_count: number; campaigns: CampaignRow[];
  target_id: string; target_title?: string; revision_number?: number | null;
  revision_date?: string | null; completion_percent: number }
type EmployeeRow = Metrics & { employee_id: string; bitrix_id: number; first_name: string;
  last_name: string; department_ids: number[]; completion_percent: number }
type Overview = { summary: Summary; rows: (TargetRow | EmployeeRow)[]; total: number; offset: number; limit: number }
type Attempt = { id: string; status: string; attempt_no: number; correct_count: number | null;
  auto_count: number | null; reward_points?: number; review_id: string | null }
type Assignment = { id: string; campaign_id: string; campaign_title: string; target_type: string;
  target_title?: string; revision_number?: number | null; reviewer_names?: string[];
  confirmation_method?: string | null;
  employee_id: string; employee_name: string; bitrix_id: number; department_ids: number[];
  status: string; is_overdue: boolean; assigned_at: string; due_at: string | null;
  completed_at: string | null; attempts: Attempt[] }
type AssignmentPage = { rows: Assignment[]; total: number; offset: number; limit: number }
type Department = { id: number; parent_id: number | null; title: string }
type Reviewer = { bitrix_id: number; name: string }

const root = '/education-next/api/admin'
const statusNames: Record<string, string> = {
  not_started: 'Не приступил', in_progress: 'В процессе', pending_review: 'Ожидает проверки',
  returned: 'Возвращено', completed: 'Завершено', exempted: 'Освобождён',
  cancelled: 'Отменено', overdue: 'Просрочено',
}
const targetNames: Record<string, string> = {
  article_revision: 'Редакция статьи', course_article: 'Статья курса', course_test: 'Тест курса', course: 'Курс',
}
const methodNames: Record<string, string> = { button: 'Кнопкой', test: 'Тестом', manual: 'Вручную' }
const PAGE = 30
type SavedFilters = { group?: Group; search?: string; departmentId?: string; status?: string;
  targetType?: string; dueFrom?: string; dueTo?: string; progressBand?: string;
  mine?: boolean; reviewerId?: string; revisionNumber?: string; confirmationMethod?: string }

function savedFilters(context: Domain): SavedFilters {
  try {
    const value = JSON.parse(sessionStorage.getItem(`review-center:${context}`) || '{}') as SavedFilters
    return value && typeof value === 'object' ? value : {}
  } catch { return {} }
}

function dateLabel(value: string | null): string {
  return value ? new Date(value).toLocaleDateString('ru-RU') : 'Без срока'
}

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${root}${path}`, { credentials: 'include', signal })
  if (!response.ok) throw new Error(`Не удалось загрузить данные (${response.status}).`)
  return response.json() as Promise<T>
}

function personName(row: EmployeeRow): string {
  return `${row.first_name} ${row.last_name}`.trim()
}

function MetricsStrip({ summary, context }: { summary: Summary; context: Domain }) {
  const items = [
    ['Сотрудников', summary.employees], ['Назначений', summary.assignments],
    ['Завершено', summary.completed], ['В процессе', summary.in_progress],
    ['Ждут проверки', summary.pending_review], ['Просрочено', summary.overdue],
    ['Не приступили', summary.not_started],
    ['Возвращено', summary.returned], ['Освобождено', summary.exempted],
    ...(context === 'courses' ? [['Средний прогресс', `${summary.progress_percent}%`] as const] : []),
  ] as const
  return <div className="review-metrics" aria-label="Показатели назначений">{items.map(([label, value]) =>
    <div key={label}><small>{label}</small><strong>{value}</strong></div>)}</div>
}

export default function ReviewOverview({ context, onOpenReview }: {
  context: Domain; onOpenReview: (id: string) => void
}) {
  const [saved] = useState(() => savedFilters(context))
  const [group, setGroup] = useState<Group>(saved.group === 'employees' ? 'employees' : 'targets')
  const [search, setSearch] = useState(saved.search || '')
  const [departmentId, setDepartmentId] = useState(saved.departmentId || '')
  const [status, setStatus] = useState(saved.status || '')
  const [targetType, setTargetType] = useState(saved.targetType || '')
  const [dueFrom, setDueFrom] = useState(saved.dueFrom || '')
  const [dueTo, setDueTo] = useState(saved.dueTo || '')
  const [progressBand, setProgressBand] = useState(saved.progressBand || '')
  const [mine, setMine] = useState(Boolean(saved.mine))
  const [reviewerId, setReviewerId] = useState(saved.reviewerId || '')
  const [revisionNumber, setRevisionNumber] = useState(saved.revisionNumber || '')
  const [confirmationMethod, setConfirmationMethod] = useState(saved.confirmationMethod || '')
  const [offset, setOffset] = useState(0)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [departments, setDepartments] = useState<Department[]>([])
  const [reviewers, setReviewers] = useState<Reviewer[]>([])
  const [selection, setSelection] = useState<{ id: string; name: string; group: Group } | null>(null)
  const [selectedAssignment, setSelectedAssignment] = useState<string | null>(null)
  const [assignments, setAssignments] = useState<AssignmentPage | null>(null)
  const [assignmentOffset, setAssignmentOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')

  useEffect(() => {
    sessionStorage.setItem(`review-center:${context}`, JSON.stringify({ group, search, departmentId,
      status, targetType, dueFrom, dueTo, progressBand, mine, reviewerId,
      revisionNumber, confirmationMethod }))
  }, [context, group, search, departmentId, status, targetType, dueFrom, dueTo,
    progressBand, mine, reviewerId, revisionNumber, confirmationMethod])

  useEffect(() => {
    const controller = new AbortController()
    get<Department[]>('/employees/departments', controller.signal).then(setDepartments)
      .catch(cause => { if (!controller.signal.aborted) setError((cause as Error).message) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    get<Reviewer[]>(`/review-center/reviewers?context=${context}`, controller.signal).then(setReviewers)
      .catch(cause => { if (!controller.signal.aborted) setError((cause as Error).message) })
    return () => controller.abort()
  }, [context])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ context, group, search, limit: String(PAGE), offset: String(offset) })
      if (departmentId) params.set('department_id', departmentId)
      if (status) params.set('status', status)
      if (context === 'materials' && targetType) params.set('target_type', targetType)
      if (dueFrom) params.set('due_from', new Date(`${dueFrom}T00:00:00`).toISOString())
      if (dueTo) params.set('due_to', new Date(`${dueTo}T23:59:59`).toISOString())
      if (context === 'courses' && progressBand) params.set('progress_band', progressBand)
      if (mine) params.set('mine', 'true')
      if (reviewerId) params.set('reviewer_bitrix_id', reviewerId)
      if (context === 'materials' && revisionNumber) params.set('revision_number', revisionNumber)
      if (context === 'materials' && confirmationMethod) params.set('confirmation_method', confirmationMethod)
      setOverview(null)
      get<Overview>(`/review-center/overview?${params}`, controller.signal)
        .then(value => { setOverview(value); setError('') })
        .catch(cause => { if (!controller.signal.aborted) setError((cause as Error).message) })
    }, search ? 250 : 0)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [context, group, search, departmentId, status, targetType, dueFrom, dueTo, progressBand, mine, reviewerId, revisionNumber, confirmationMethod, offset])

  useEffect(() => {
    if (!selection) return
    const controller = new AbortController()
    const params = new URLSearchParams({ context, limit: String(PAGE), offset: String(assignmentOffset), search })
    params.set(selection.group === 'targets' ? 'campaign_id' : 'employee_id', selection.id)
    if (departmentId) params.set('department_id', departmentId)
    if (status) params.set('status', status)
    if (context === 'materials' && targetType) params.set('target_type', targetType)
    if (dueFrom) params.set('due_from', new Date(`${dueFrom}T00:00:00`).toISOString())
    if (dueTo) params.set('due_to', new Date(`${dueTo}T23:59:59`).toISOString())
    if (context === 'courses' && progressBand) params.set('progress_band', progressBand)
    if (mine) params.set('mine', 'true')
    if (reviewerId) params.set('reviewer_bitrix_id', reviewerId)
    if (context === 'materials' && revisionNumber) params.set('revision_number', revisionNumber)
    if (context === 'materials' && confirmationMethod) params.set('confirmation_method', confirmationMethod)
    get<AssignmentPage>(`/review-center/assignments?${params}`, controller.signal)
      .then(value => { setAssignments(value); setError('') })
      .catch(cause => { if (!controller.signal.aborted) setError((cause as Error).message) })
    return () => controller.abort()
  }, [context, selection, search, departmentId, status, targetType, dueFrom, dueTo, progressBand, mine, reviewerId, revisionNumber, confirmationMethod, assignmentOffset, refresh])

  function switchGroup(value: Group) { setOverview(null); setGroup(value); setSelection(null); setSelectedAssignment(null); setOffset(0); setAssignmentOffset(0) }
  function reset() { setSearch(''); setDepartmentId(''); setStatus(''); setTargetType(''); setDueFrom(''); setDueTo(''); setProgressBand(''); setMine(false); setReviewerId(''); setRevisionNumber(''); setConfirmationMethod(''); setOffset(0); setAssignmentOffset(0); setSelection(null); setSelectedAssignment(null) }
  function resetPages() { setOffset(0); setAssignmentOffset(0); setAssignments(null) }

  return <div className="review-overview">
    <div className="review-campaign-scope" aria-label="Состояние кампаний">
      <button className="active" aria-current="page">Активные</button>
      <button disabled title="Просмотр завершённых кампаний появится в следующей версии">Завершённые · скоро</button>
    </div>
    <div className="review-group-tabs" aria-label="Группировка проверок">
      <button className={group === 'targets' ? 'active' : ''} onClick={() => switchGroup('targets')}>
        {context === 'courses' ? 'По курсам' : 'По документам'}</button>
      <button className={group === 'employees' ? 'active' : ''} onClick={() => switchGroup('employees')}>По сотрудникам</button>
    </div>
    <div className="review-filters">
      <input aria-label="Поиск по документу или сотруднику" value={search} onChange={event => { setSearch(event.target.value); resetPages() }} placeholder="Поиск по документу или сотруднику" />
      <select aria-label="Подразделение" value={departmentId} onChange={event => { setDepartmentId(event.target.value); resetPages() }}>
        <option value="">Все подразделения</option>{departments.map(row => <option key={row.id} value={row.id}>{row.title}</option>)}
      </select>
      <select aria-label="Статус назначения" value={status} onChange={event => { setStatus(event.target.value); resetPages() }}>
        <option value="">Все статусы</option>{Object.entries(statusNames).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select>
      {context === 'materials' && <select aria-label="Тип материала" value={targetType} onChange={event => { setTargetType(event.target.value); resetPages() }}>
        <option value="">Все типы</option><option value="article_revision">Статья Базы знаний</option>
        <option value="course_article">Статья курса</option><option value="course_test">Тест курса</option>
      </select>}
      {context === 'courses' && <select aria-label="Прогресс курса" value={progressBand} onChange={event => { setProgressBand(event.target.value); resetPages() }}>
        <option value="">Любой прогресс</option>{['0', '1-25', '26-50', '51-75', '76-99', '100'].map(value =>
          <option key={value} value={value}>{value}%</option>)}
      </select>}
      <label className="review-date">Срок от<input aria-label="Срок от" type="date" value={dueFrom} max={dueTo || undefined} onChange={event => { setDueFrom(event.target.value); resetPages() }} /></label>
      <label className="review-date">Срок до<input aria-label="Срок до" type="date" value={dueTo} min={dueFrom || undefined} onChange={event => { setDueTo(event.target.value); resetPages() }} /></label>
      <label className="review-mine"><input aria-label="Мои кампании" type="checkbox" checked={mine} onChange={event => { setMine(event.target.checked); resetPages() }} /> Мои кампании</label>
      <select aria-label="Ответственный преподаватель" value={reviewerId} onChange={event => { setReviewerId(event.target.value); resetPages() }}>
        <option value="">Все ответственные</option>{reviewers.map(person => <option key={person.bitrix_id} value={person.bitrix_id}>{person.name}</option>)}
      </select>
      {context === 'materials' && <input aria-label="Номер редакции" type="number" min="1" value={revisionNumber} onChange={event => { setRevisionNumber(event.target.value); resetPages() }} placeholder="Номер редакции" />}
      {context === 'materials' && <select aria-label="Способ подтверждения" value={confirmationMethod} onChange={event => { setConfirmationMethod(event.target.value); resetPages() }}>
        <option value="">Все способы</option><option value="button">Кнопкой</option>
        <option value="test">Тестом</option><option value="manual">Вручную</option>
      </select>}
      <button className="review-reset" onClick={reset}>Сбросить фильтры</button>
    </div>
    {error && <div className="error" role="alert">{error}</div>}
    {overview && <MetricsStrip summary={overview.summary} context={context} />}
    {selectedAssignment ? <ReviewAssignment id={selectedAssignment} onBack={() => { setSelectedAssignment(null); setRefresh(value => value + 1) }} onOpenReview={onOpenReview} /> : selection ? <div className="review-selection">
      <button className="back" onClick={() => setSelection(null)}>← Назад к списку</button>
      <div className="heading"><div><h2>{selection.name}</h2><p>Назначения только из активных кампаний этого раздела.</p></div></div>
      {!assignments ? <p role="status">Загружаем назначения…</p> : <>
        <p className="review-count">Отображено {assignments.rows.length} из {assignments.total}</p>
        <div className="table"><table><thead><tr><th>{selection.group === 'employees' ? 'Материал / курс' : 'Сотрудник'}</th><th>Кампания</th><th>Статус</th><th>Подтверждение</th><th>Срок</th><th>Попытки</th><th></th></tr></thead><tbody>
          {assignments.rows.map(row => <tr key={row.id}><td>{selection.group === 'employees'
            ? <><b>{row.target_title || row.campaign_title}</b>{row.revision_number && <small>Редакция № {row.revision_number}</small>}</>
            : <>{row.employee_name} <small>#{row.bitrix_id}</small></>}</td>
            <td>{row.campaign_title}{row.reviewer_names?.length ? <small>Ответственные: {row.reviewer_names.join(', ')}</small> : null}</td>
            <td>{statusNames[row.status] ?? row.status}{row.is_overdue && ' · просрочено'}</td>
            <td>{row.confirmation_method ? methodNames[row.confirmation_method] || row.confirmation_method : '—'}</td>
            <td>{dateLabel(row.due_at)}<small>Назначено {dateLabel(row.assigned_at)}</small></td><td>{row.attempts.length ? row.attempts.map(attempt =>
              <span key={attempt.id} className="review-attempt">№ {attempt.attempt_no} · {attempt.correct_count ?? '—'}/{attempt.auto_count ?? '—'}
                {Boolean(attempt.reward_points) && ` · +${attempt.reward_points} баллов`}
                {attempt.review_id && <button onClick={() => onOpenReview(attempt.review_id!)}>Открыть ответы</button>}</span>) : '—'}</td>
            <td><button onClick={() => setSelectedAssignment(row.id)}>Карточка</button></td></tr>)}
        </tbody></table>{assignments.rows.length === 0 && <div className="empty">Назначений по фильтру нет.</div>}</div>
        {assignments.total > PAGE && <div className="review-pages"><button disabled={assignmentOffset === 0} onClick={() => setAssignmentOffset(Math.max(0, assignmentOffset - PAGE))}>Назад</button>
          <span>{assignmentOffset + 1}–{Math.min(assignmentOffset + PAGE, assignments.total)} из {assignments.total}</span>
          <button disabled={assignmentOffset + PAGE >= assignments.total} onClick={() => setAssignmentOffset(assignmentOffset + PAGE)}>Далее</button></div>}
      </>}
    </div> : !overview ? <p role="status">Загружаем кампании…</p> : <>
      <p className="review-count">Отображено {overview.rows.length} из {overview.total}</p>
      {group === 'targets' ? <div className="review-target-list">{(overview.rows as TargetRow[]).map(target =>
        <section className="review-target-card" key={`${target.target_type}:${target.target_id}`}>
          <div className="review-target-head"><div><h3>{target.target_title}</h3>
            <p>{targetNames[target.target_type] ?? target.target_type}{target.revision_number ? ` · редакция № ${target.revision_number}` : ''}
              {target.revision_date && ` · ${dateLabel(target.revision_date)}`}</p></div>
            <span>{target.campaign_count} кампаний · {target.assignments} назначений · {target.completed} завершено</span></div>
          <div className="table"><table><thead><tr><th>Активная кампания</th><th>Участники</th><th>Завершено</th><th>В процессе</th>{context === 'courses' && <th>Прогресс</th>}<th>Просрочено</th><th>Срок</th><th></th></tr></thead><tbody>
            {target.campaigns.map(campaign => <tr key={campaign.campaign_id}><td><b>{campaign.campaign_title}</b><small>#{campaign.campaign_id.slice(0, 8)} · запуск {dateLabel(campaign.launched_at)}</small></td>
              <td>{campaign.assignments}</td><td>{campaign.completed} · {campaign.completion_percent}%</td>
              <td>{campaign.in_progress + campaign.pending_review + campaign.returned}</td>
              {context === 'courses' && <td>{campaign.progress_percent}%</td>}
              <td>{campaign.overdue}</td><td>{dateLabel(campaign.campaign_due_at)}</td>
              <td><button onClick={() => { setAssignments(null); setAssignmentOffset(0); setSelection({ id: campaign.campaign_id, name: campaign.campaign_title, group }) }}>Открыть</button></td></tr>)}
          </tbody></table></div>
        </section>)}</div> : <div className="table"><table><thead><tr><th>Сотрудник</th><th>Назначено</th><th>Завершено</th><th>В процессе</th>{context === 'courses' && <th>Прогресс</th>}<th>Просрочено</th><th></th></tr></thead><tbody>
          {(overview.rows as EmployeeRow[]).map(person => <tr key={person.employee_id}><td><span className="review-person"><span className="review-avatar" aria-hidden="true">{person.first_name.slice(0, 1)}{person.last_name.slice(0, 1)}</span><span><b>{personName(person)}</b>
            <small>{person.department_ids.map(id => departments.find(item => item.id === id)?.title).filter(Boolean).join(', ') || `Битрикс24 #${person.bitrix_id}`}</small></span></span></td>
            <td>{person.assignments}</td><td>{person.completed}</td>
            <td>{person.in_progress + person.pending_review + person.returned}</td>
            {context === 'courses' && <td>{person.progress_percent}%</td>}
            <td>{person.overdue}</td>
            <td><button onClick={() => { setAssignments(null); setAssignmentOffset(0); setSelection({ id: person.employee_id, name: personName(person), group }) }}>Открыть</button></td></tr>)}
        </tbody></table></div>}{overview.rows.length === 0 && <div className="empty">Активных назначений по фильтру нет.</div>}
      {overview.total > PAGE && <div className="review-pages"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Назад</button>
        <span>{offset + 1}–{Math.min(offset + PAGE, overview.total)} из {overview.total}</span>
        <button disabled={offset + PAGE >= overview.total} onClick={() => setOffset(offset + PAGE)}>Далее</button></div>}
    </>}
  </div>
}
