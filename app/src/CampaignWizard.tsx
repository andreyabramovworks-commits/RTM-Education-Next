import { useEffect, useState } from 'react'

type Person = { bitrix_id: number; name: string; can_review: boolean }
type Department = { id: number; parent_id: number | null; title: string }
export type Campaign = { id: string; target_id?: string; title: string; status: string; recipient_count: number;
  include_new_employees?: boolean; has_department_rule?: boolean }
type Assignment = { id: string; employee_name: string; employee_bitrix_id: number; status: string; due_at: string | null; is_overdue: boolean }
type Delivery = { jobs: { id: string; employee_name: string; kind: string; status: string; attempts: number; last_error: string | null; external_id: string | null }[]; counts: Record<string, number> }
type CampaignPreview = { recipient_count: number; example_recipient: string; due_at: string | null;
  relative_due_is_estimate: boolean; task_title: string | null; task_description: string | null;
  duplicates_excluded: number; duplicate_recipients: string[]; inactive_excluded: { bitrix_id: number; name: string }[];
  recipients: { bitrix_id: number; name: string; source: 'individual' | 'department';
    due_at: string | null; task_title: string | null; task_description: string | null }[] }
const api = '/education-next/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${api}${path}`, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) throw new Error(`Не удалось сохранить кампанию (${response.status}).`)
  return response.json() as Promise<T>
}

function RecipientPreview({ preview }: { preview: CampaignPreview }) {
  return <details className="recipient-preview"><summary>Все получатели и задачи ({preview.recipient_count})</summary>
    <p>Повторных назначений исключено: {preview.duplicates_excluded || 0}{preview.duplicate_recipients?.length ? ` (${preview.duplicate_recipients.join(', ')})` : ''}.{preview.relative_due_is_estimate ? ' Срок рассчитан для предпросмотра и уточнится при запуске.' : ''}</p>
    <p>Неактивных сотрудников отдела исключено: {preview.inactive_excluded?.length || 0}{preview.inactive_excluded?.length ? ` (${preview.inactive_excluded.map(person => person.name).join(', ')})` : ''}.</p>
    <div className="table"><table><thead><tr><th>Сотрудник</th><th>Источник</th><th>Срок</th><th>Задача Bitrix24</th></tr></thead>
      <tbody>{(preview.recipients || []).map(recipient => <tr key={recipient.bitrix_id}><td>{recipient.name} <small>#{recipient.bitrix_id}</small></td>
        <td>{recipient.source === 'individual' ? 'Личный выбор' : 'Подразделение'}</td>
        <td>{recipient.due_at ? new Date(recipient.due_at).toLocaleString('ru-RU') : '—'}</td>
        <td>{recipient.task_title ? <><strong>{recipient.task_title}</strong><p>{recipient.task_description}</p></> : 'Выключена'}</td></tr>)}</tbody>
    </table></div>
  </details>
}

export default function CampaignWizard({ targetType = 'course', targetId, targetTitle, initialCampaign, onBack }: {
  targetType?: 'course' | 'course_article' | 'course_test' | 'article_revision'; targetId: string; targetTitle: string;
  initialCampaign?: Campaign | null; onBack: () => void
}) {
  const [search, setSearch] = useState('')
  const [people, setPeople] = useState<Person[]>([])
  const [departments, setDepartments] = useState<Department[]>([])
  const [selectedDepartments, setSelectedDepartments] = useState<number[]>([])
  const [includeSubdepartments, setIncludeSubdepartments] = useState(false)
  const [includeNewEmployees, setIncludeNewEmployees] = useState(false)
  const [selected, setSelected] = useState<Person[]>([])
  const [reviewers, setReviewers] = useState<Person[]>([])
  const [mode, setMode] = useState<'relative' | 'absolute'>('relative')
  const [days, setDays] = useState(7)
  const [absolute, setAbsolute] = useState('')
  const [notify, setNotify] = useState(false)
  const [task, setTask] = useState(false)
  const [taskTitle, setTaskTitle] = useState(targetType === 'course'
    ? 'Пройти курс «{course}» — {name}' : 'Изучить материал «{course}» — {name}')
  const [taskDescription, setTaskDescription] = useState(targetType === 'course'
    ? 'Откройте {link} и пройдите курс «{course}» до {due_date}.'
    : 'Откройте {link} и изучите материал «{course}» до {due_date}.')
  const [draft, setDraft] = useState<Campaign | null>(initialCampaign ?? null)
  const [preview, setPreview] = useState<CampaignPreview | null>(null)
  const [assignments, setAssignments] = useState<Assignment[] | null>(null)
  const [delivery, setDelivery] = useState<Delivery | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      request<Person[]>(`/admin/employees/recipients?search=${encodeURIComponent(search)}`)
        .then(rows => { if (active) setPeople(rows) })
        .catch(e => { if (active) setError((e as Error).message) })
    }, 200)
    return () => { active = false; clearTimeout(timer) }
  }, [search])

  useEffect(() => {
    request<Department[]>('/admin/employees/departments').then(setDepartments).catch(e => setError((e as Error).message))
  }, [])

  useEffect(() => {
    if (!draft || draft.status !== 'draft') return
    let active = true
    request<CampaignPreview>(`/admin/campaigns/${draft.id}/preview`)
      .then(value => { if (active) setPreview(value) })
      .catch(e => { if (active) setError((e as Error).message) })
    return () => { active = false }
  }, [draft])

  function toggle(person: Person, list: Person[], setter: (next: Person[]) => void) {
    setter(list.some(row => row.bitrix_id === person.bitrix_id)
      ? list.filter(row => row.bitrix_id !== person.bitrix_id) : [...list, person])
  }

  async function saveDraft() {
    if (!selected.length && !selectedDepartments.length) { setError('Выберите сотрудников или подразделение.'); return }
    if (mode === 'absolute' && !absolute) { setError('Укажите дату и время окончания.'); return }
    setBusy(true); setError('')
    try {
      const saved = await request<Campaign>('/admin/campaigns', { method: 'POST', body: JSON.stringify({
        target_type: targetType, target_id: targetId, title: targetTitle,
        recipient_bitrix_ids: selected.map(row => row.bitrix_id), reviewer_bitrix_ids: reviewers.map(row => row.bitrix_id),
        department_ids: selectedDepartments, include_subdepartments: includeSubdepartments,
        include_new_employees: selectedDepartments.length > 0 && includeNewEmployees,
        due_mode: mode, due_days: mode === 'relative' ? days : null,
        due_at: mode === 'absolute' ? new Date(absolute).toISOString() : null,
        notify_enabled: notify, task_enabled: task, task_title: task ? taskTitle : '', task_description: task ? taskDescription : '',
      }) })
      setDraft(saved)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function launch() {
    if (!draft || !window.confirm(`Запустить обучение для ${draft.recipient_count} сотрудников?`)) return
    setBusy(true); setError('')
    try {
      const launched = await request<Campaign>(`/admin/campaigns/${draft.id}/launch`, { method: 'POST', body: JSON.stringify({ confirmed: true }) })
      setDraft(launched)
      setDelivery(await request<Delivery>(`/admin/campaigns/${launched.id}/delivery`))
    }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function loadAssignments() {
    if (!draft) return
    setBusy(true); setError('')
    try { setAssignments(await request<Assignment[]>(`/admin/campaigns/${draft.id}/assignments`)) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function loadDelivery() {
    if (!draft) return
    setBusy(true); setError('')
    try { setDelivery(await request<Delivery>(`/admin/campaigns/${draft.id}/delivery`)) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function addRecipients() {
    if (!draft || !selected.length) return
    const reason = window.prompt('Почему добавляем сотрудников в запущенную кампанию?')?.trim()
    if (!reason) return
    if (reason.length < 10) { setError('Причина должна быть не короче 10 символов.'); return }
    if (!window.confirm(`Добавить ${selected.length} сотрудников? Уже назначенные повторно добавлены не будут.`)) return
    setBusy(true); setError('')
    try {
      const result = await request<{ added_ids: number[]; already_assigned_ids: number[]; recipient_count: number }>(
        `/admin/campaigns/${draft.id}/recipients`, { method: 'POST', body: JSON.stringify({
          recipient_bitrix_ids: selected.map(row => row.bitrix_id), reason, confirmed: true,
        }) })
      setDraft({ ...draft, recipient_count: result.recipient_count })
      setSelected([])
      setAssignments(await request<Assignment[]>(`/admin/campaigns/${draft.id}/assignments`))
      setDelivery(await request<Delivery>(`/admin/campaigns/${draft.id}/delivery`))
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function changeNewEmployees() {
    if (!draft) return
    const enabled = !draft.include_new_employees
    const reason = window.prompt(enabled
      ? 'Причина включения автоматических назначений новым сотрудникам'
      : 'Причина отключения автоматических назначений')?.trim()
    if (!reason) return
    if (reason.length < 10) { setError('Причина должна быть не короче 10 символов.'); return }
    if (!window.confirm(`${enabled ? 'Включить' : 'Отключить'} назначения новым сотрудникам выбранных подразделений?`)) return
    setBusy(true); setError('')
    try {
      const updated = await request<Campaign>(`/admin/campaigns/${draft.id}/new-employees`, {
        method: 'PUT', body: JSON.stringify({ enabled, reason, confirmed: true }),
      })
      setDraft(updated)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function retryJob(id: string) {
    const reason = window.prompt('Причина повторной доставки')?.trim()
    if (!reason) return
    if (reason.length < 10) { setError('Причина должна быть не короче 10 символов.'); return }
    if (!window.confirm('Повторить доставку после устранения причины ошибки?')) return
    setBusy(true); setError('')
    try {
      await request(`/admin/outbox/${id}/retry`, { method: 'POST', body: JSON.stringify({ reason, confirmed: true }) })
      if (draft) setDelivery(await request<Delivery>(`/admin/campaigns/${draft.id}/delivery`))
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function decide(assignment: Assignment, action: 'exempt' | 'confirm-complete' | 'due') {
    const reason = window.prompt(`Причина для сотрудника ${assignment.employee_name}`)?.trim()
    if (!reason) return
    if (reason.length < 10) { setError('Причина должна быть не короче 10 символов.'); return }
    let dueAt: string | undefined
    if (action === 'due') {
      const value = window.prompt('Новый срок: ГГГГ-ММ-ДД ЧЧ:ММ', assignment.due_at?.slice(0, 16).replace('T', ' ') || '')
      if (!value) return
      const parsed = new Date(value.replace(' ', 'T'))
      if (Number.isNaN(parsed.getTime())) { setError('Не удалось прочитать дату и время.'); return }
      dueAt = parsed.toISOString()
    }
    if (!window.confirm(`Подтвердить действие для ${assignment.employee_name}?`)) return
    setBusy(true); setError('')
    try {
      await request(`/admin/assignments/${assignment.id}/${action}`, { method: action === 'due' ? 'PUT' : 'POST',
        body: JSON.stringify({ reason, confirmed: true, due_at: dueAt }) })
      await loadAssignments()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return <>
    <button className="back" onClick={onBack}>← Назад</button>
    <div className="heading"><div><h1>{targetType === 'course' ? 'Назначить обучение' : targetType === 'article_revision' ? 'Назначить обновление' : 'Назначить материал'}</h1><p>{targetTitle}</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    {draft?.status === 'active' ? <div className="panel"><h2>Кампания запущена</h2><p>Назначений: {draft.recipient_count}. Доставка уведомлений и задач обрабатывается отдельно.</p><div className="course-actions"><button disabled={busy} onClick={loadAssignments}>Показать назначения</button><button disabled={busy} onClick={loadDelivery}>Статус доставки</button><button onClick={onBack}>{targetType === 'course' ? 'Вернуться к курсу' : 'Вернуться к материалам'}</button></div>{delivery && <div className="delivery-status"><p>Доставка: отправлено {delivery.counts.sent || 0}, ожидает {Number(delivery.counts.pending || 0) + Number(delivery.counts.retry || 0) + Number(delivery.counts.sending || 0)}, ошибки {Number(delivery.counts.failed || 0) + Number(delivery.counts.uncertain || 0)}.</p><div className="table"><table><thead><tr><th>Сотрудник</th><th>Тип</th><th>Статус</th><th>Попытки</th><th>Действие</th></tr></thead><tbody>{delivery.jobs.map(job => <tr key={job.id}><td>{job.employee_name}</td><td>{job.kind === 'bitrix_task' ? 'Задача' : 'Уведомление'}</td><td>{job.status}{job.last_error ? ` · ${job.last_error}` : ''}</td><td>{job.attempts}</td><td>{job.status === 'failed' && <button disabled={busy} onClick={() => retryJob(job.id)}>Повторить</button>}</td></tr>)}</tbody></table></div>{delivery.jobs.some(job => job.status === 'uncertain') && <p>Результат части запросов неизвестен. Проверьте их в Битрикс24 перед повторной отправкой.</p>}</div>}{assignments && <div className="table"><table><thead><tr><th>Сотрудник</th><th>Статус</th><th>Срок</th><th>Действия</th></tr></thead><tbody>{assignments.map(row => <tr key={row.id}><td>{row.employee_name}</td><td>{row.status}{row.is_overdue ? ' · просрочено' : ''}</td><td>{row.due_at ? new Date(row.due_at).toLocaleString('ru-RU') : '—'}</td><td>{!['completed', 'exempted', 'cancelled'].includes(row.status) && <div className="course-actions"><button disabled={busy} onClick={() => decide(row, 'due')}>Изменить срок</button><button disabled={busy} onClick={() => decide(row, 'exempt')}>Освободить</button><button disabled={busy} onClick={() => decide(row, 'confirm-complete')}>Подтвердить вручную</button></div>}</td></tr>)}</tbody></table></div>}</div> : draft ? <div className="panel"><h2>Черновик кампании сохранён</h2><p>Получателей: {preview?.recipient_count ?? draft.recipient_count}. Выпуск материала и запуск кампании — разные действия.</p>{preview && <RecipientPreview preview={preview} />}{preview?.task_title && <div className="panel"><h3>Предпросмотр задачи для {preview.example_recipient}</h3><p><strong>{preview.task_title}</strong></p><p>{preview.task_description}</p><p>Срок: {preview.due_at ? new Date(preview.due_at).toLocaleString('ru-RU') : '—'}{preview.relative_due_is_estimate ? ' · будет рассчитан при запуске' : ''}</p></div>}<button className="primary" disabled={busy || !preview} onClick={launch}>Подтвердить запуск</button></div> : <div className="campaign-form">
      <section className="panel"><h2>Получатели</h2><p>Сотрудники и подразделения объединяются без дублей. Итоговое количество покажем после сохранения черновика.</p><label>Подразделения<select aria-label="Подразделения" value="" onChange={e => { const id = Number(e.target.value); if (id && !selectedDepartments.includes(id)) setSelectedDepartments(current => [...current, id]) }}><option value="">Выберите подразделение</option>{departments.map(department => <option key={department.id} value={department.id}>{department.title}</option>)}</select></label>{selectedDepartments.map(id => <button key={id} className="department-chip" onClick={() => setSelectedDepartments(current => current.filter(value => value !== id))}>{departments.find(row => row.id === id)?.title || id} ×</button>)}{selectedDepartments.length > 0 && <><label><input type="checkbox" checked={includeSubdepartments} onChange={e => setIncludeSubdepartments(e.target.checked)} /> Включить подотделы</label><label><input type="checkbox" checked={includeNewEmployees} onChange={e => setIncludeNewEmployees(e.target.checked)} /> Назначать новым сотрудникам после запуска</label><p>Новыми считаются сотрудники, впервые появившиеся в синхронизации Bitrix24 после включения правила.</p></>}<input aria-label="Найти сотрудника" placeholder="Имя или ID Битрикс24" value={search} onChange={e => setSearch(e.target.value)} /><div className="campaign-people">{people.map(person => <label key={person.bitrix_id}><input type="checkbox" checked={selected.some(row => row.bitrix_id === person.bitrix_id)} onChange={() => toggle(person, selected, setSelected)} />{person.name} <small>#{person.bitrix_id}</small></label>)}</div></section>
      <section className="panel"><h2>Ответственные за проверку</h2><p>Выберите преподавателей для маршрутизации ответов.</p><div className="campaign-people">{people.filter(person => person.can_review).map(person => <label key={person.bitrix_id}><input type="checkbox" checked={reviewers.some(row => row.bitrix_id === person.bitrix_id)} onChange={() => toggle(person, reviewers, setReviewers)} />{person.name}</label>)}</div></section>
      <section className="panel"><h2>Срок</h2><label><input type="radio" checked={mode === 'relative'} onChange={() => setMode('relative')} /> Через указанное число дней после назначения</label>{mode === 'relative' && <input aria-label="Дней до срока" type="number" min="1" max="3650" value={days} onChange={e => setDays(Number(e.target.value))} />}<label><input type="radio" checked={mode === 'absolute'} onChange={() => setMode('absolute')} /> Конкретная дата и время</label>{mode === 'absolute' && <input aria-label="Дата и время окончания" type="datetime-local" value={absolute} onChange={e => setAbsolute(e.target.value)} />}</section>
      <section className="panel"><h2>Уведомления и задачи</h2><label><input type="checkbox" checked={notify} onChange={e => setNotify(e.target.checked)} /> Отправить уведомление Bitrix24</label><label><input type="checkbox" checked={task} onChange={e => setTask(e.target.checked)} /> Создать задачу Bitrix24</label>{task && <><p>Поля: {'{course}'}, {'{name}'}, {'{due_date}'}, {'{link}'}. После сохранения покажем текст задачи для одного получателя.</p><label>Название задачи<input value={taskTitle} onChange={e => setTaskTitle(e.target.value)} /></label><label>Описание задачи<textarea value={taskDescription} onChange={e => setTaskDescription(e.target.value)} /></label></>}</section>
      <section className="panel"><h2>Проверка перед запуском</h2><p>Сотрудников выбрано: {selected.length}; подразделений: {selectedDepartments.length}. Срок: {mode === 'relative' ? `через ${days} дн.` : absolute || 'не указан'}. Уведомления: {notify ? 'включены' : 'выключены'}. Задачи: {task ? 'включены' : 'выключены'}.</p>{task && <p>Задача: {taskTitle} — {taskDescription}</p>}<button className="primary" disabled={busy || (!selected.length && !selectedDepartments.length)} onClick={saveDraft}>Сохранить черновик кампании</button></section>
    </div>}
    {draft?.status === 'active' && <section className="panel"><h2>Добавить сотрудников</h2><p>Новое назначение создаётся только для тех, кто ещё не участвует в этой кампании. Действие сохраняется с причиной.</p><input aria-label="Найти сотрудника для кампании" placeholder="Имя или ID Битрикс24" value={search} onChange={e => setSearch(e.target.value)} /><div className="campaign-people">{people.map(person => <label key={person.bitrix_id}><input type="checkbox" checked={selected.some(row => row.bitrix_id === person.bitrix_id)} onChange={() => toggle(person, selected, setSelected)} />{person.name} <small>#{person.bitrix_id}</small></label>)}</div><button disabled={busy || selected.length === 0} onClick={addRecipients}>Добавить выбранных ({selected.length})</button></section>}
    {draft?.status === 'active' && draft.has_department_rule && <section className="panel"><h2>Новые сотрудники</h2><p>Сейчас автоматическое назначение {draft.include_new_employees ? 'включено' : 'выключено'}. При следующей синхронизации Битрикс24 новое назначение получит сотрудник, впервые замеченный после включения правила и попавший в выбранное подразделение.</p><button disabled={busy} onClick={changeNewEmployees}>{draft.include_new_employees ? 'Отключить' : 'Включить'} назначения новым сотрудникам</button></section>}
  </>
}
