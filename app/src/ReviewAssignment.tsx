import { useEffect, useState } from 'react'

type Attempt = { id: string; attempt_no: number; course_item_id: string | null; status: string;
  correct_count: number | null; auto_count: number | null; reward_points?: number;
  started_at: string; review_id: string | null }
type History = { id: string; action: string; reason: string; occurred_at: string; details: Record<string, unknown> }
type Section = { id: string; title: string; items: { id: string; title: string; kind: string;
  required: boolean; completed_at: string | null }[] }
type Detail = { id: string; employee_name: string; bitrix_id: number; campaign_title: string;
  department_titles?: string[];
  target_title: string; target_type: string; status: string; is_overdue: boolean;
  assigned_at: string; due_at: string | null; completed_at: string | null;
  revision_number: number | null; revision_date: string | null;
  course_updated_at?: string | null;
  required_total: number; required_done: number; sections: Section[];
  attempts: Attempt[]; history: History[] }

type Action = 'due' | 'exempt' | 'confirm' | 'attempt' | 'remind'
const root = '/education-next/api/admin'
const labels: Record<Action, string> = {
  due: 'Изменить срок', exempt: 'Освободить', confirm: 'Подтвердить вручную',
  attempt: 'Выдать попытку', remind: 'Напомнить сотруднику',
}
const statusNames: Record<string, string> = {
  not_started: 'Не приступил', in_progress: 'В процессе', pending_review: 'Ожидает проверки',
  returned: 'Возвращено', completed: 'Завершено', exempted: 'Освобождён', cancelled: 'Отменено',
}

function when(value: string | null): string {
  return value ? new Date(value).toLocaleString('ru-RU') : '—'
}

export default function ReviewAssignment({ id, onBack, onOpenReview }: {
  id: string; onBack: () => void; onOpenReview: (id: string) => void
}) {
  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState('')
  const [action, setAction] = useState<Action | null>(null)
  const [reason, setReason] = useState('')
  const [due, setDue] = useState('')
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [reminderId, setReminderId] = useState('')
  const [busy, setBusy] = useState(false)
  const pendingReview = detail?.status === 'pending_review'
    ? detail.attempts.find(row => row.review_id)?.review_id : null
  const isClosed = detail ? ['completed', 'exempted', 'cancelled'].includes(detail.status) : false

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${root}/review-center/assignments/${id}`, { credentials: 'include', signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error(`Не удалось открыть назначение (${response.status}).`)
        return response.json() as Promise<Detail>
      }).then(setDetail).catch(cause => { if (!controller.signal.aborted) setError((cause as Error).message) })
    return () => controller.abort()
  }, [id])

  function choose(next: Action, selectedAttempt: Attempt | null = null) {
    setAction(next); setAttempt(selectedAttempt); setReason(''); setDue(''); setError('')
    if (next === 'remind') setReminderId(crypto.randomUUID())
  }

  async function perform() {
    if (!detail || !action || reason.trim().length < 10) return
    const url = action === 'due' ? `/assignments/${id}/due`
      : action === 'exempt' ? `/assignments/${id}/exempt`
      : action === 'confirm' ? `/assignments/${id}/confirm-complete`
      : action === 'remind' ? `/assignments/${id}/remind`
      : attempt?.course_item_id ? `/assignments/${id}/items/${attempt.course_item_id}/attempt-allowances`
      : `/assignments/${id}/${detail.target_type === 'course_test' ? 'test' : 'revision'}/attempt-allowances`
    if (action === 'due' && !due) return
    if (!window.confirm(`${labels[action]} для ${detail.employee_name}? Причина будет записана в историю.`)) return
    setBusy(true); setError('')
    try {
      const payload = action === 'due' ? { due_at: new Date(due).toISOString(), reason: reason.trim(), confirmed: true }
        : action === 'attempt' ? { delta: 1, reason: reason.trim(), confirmed: true }
        : action === 'remind' ? { request_id: reminderId, reason: reason.trim(), confirmed: true }
        : { reason: reason.trim(), confirmed: true }
      const response = await fetch(`${root}${url}`, { method: action === 'due' ? 'PUT' : 'POST',
        credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      if (!response.ok) {
        const result = await response.json().catch(() => ({})) as { detail?: string }
        throw new Error(result.detail || `Не удалось выполнить действие (${response.status}).`)
      }
      const refreshed = await fetch(`${root}/review-center/assignments/${id}`, { credentials: 'include' })
      if (!refreshed.ok) throw new Error('Действие выполнено, но карточка не обновилась. Откройте её повторно.')
      setDetail(await refreshed.json() as Detail)
      setAction(null); setReason('')
    } catch (cause) { setError((cause as Error).message) } finally { setBusy(false) }
  }

  return <section className="review-assignment">
    <button className="back" onClick={onBack}>← Назад к назначениям</button>
    {error && <div className="error" role="alert">{error}</div>}
    {!detail ? <p role="status">Загружаем карточку…</p> : <>
      {detail.target_type === 'course' && <div className="crumb">{detail.target_title} / {detail.employee_name}</div>}
      <div className="heading"><div className="review-person"><span className="review-avatar" aria-hidden="true">{detail.employee_name.split(' ').map(part => part.slice(0, 1)).slice(0, 2).join('')}</span><div><h2>{detail.employee_name}</h2><p>{detail.department_titles?.join(', ') || `Битрикс24 #${detail.bitrix_id}`} · {detail.campaign_title}</p></div></div>
        <span className="review-state">{statusNames[detail.status] ?? detail.status}{detail.is_overdue && ' · просрочено'}</span></div>
      <div className="review-detail-grid">
        <div><small>Материал</small><b>{detail.target_title}{detail.revision_number && ` · редакция № ${detail.revision_number}`}</b></div>
        <div><small>Назначено</small><b>{when(detail.assigned_at)}</b></div>
        <div><small>Срок</small><b>{when(detail.due_at)}</b></div>
        <div><small>Завершено</small><b>{when(detail.completed_at)}</b></div>
        {detail.target_type === 'course' && <><div><small>Обязательные элементы</small><b>{detail.required_done} из {detail.required_total} · {detail.required_total ? Math.round(100 * detail.required_done / detail.required_total) : 0}%</b></div>
          <div><small>Курс обновлён</small><b>{when(detail.course_updated_at || null)}</b></div></>}
      </div>
      {detail.sections.length > 0 && <div className="review-course-program"><h3>Программа курса</h3>{detail.sections.map(section =>
        <div key={section.id}><h4>{section.title}</h4>{section.items.map(item => <p key={item.id}>
          {item.kind === 'test' ? 'Тест' : 'Статья'} · {item.title} · {item.completed_at ? `Завершено ${when(item.completed_at)}` : 'Не завершено'}
          {!item.required && ' · необязательный'}</p>)}</div>)}</div>}
      <div className="review-detail-actions">{pendingReview
        ? <button className="primary" onClick={() => onOpenReview(pendingReview)}>Проверить ответ</button>
        : <button className="primary" disabled={isClosed} title={isClosed ? 'Назначение уже закрыто' : undefined}
          onClick={() => choose('remind')}>Напомнить сотруднику</button>}
        <details><summary>Все действия</summary><div>
          {isClosed && <p>Назначение закрыто: изменение срока, напоминание и решения недоступны.</p>}
          <button disabled={isClosed} onClick={() => choose('due')}>Изменить срок</button>
          <button disabled={isClosed} onClick={() => choose('remind')}>Напомнить сотруднику</button>
          {detail.attempts.filter(row => row.review_id).map(row => <button key={row.id}
            onClick={() => onOpenReview(row.review_id!)}>Ответы попытки № {row.attempt_no}</button>)}
          <button disabled={isClosed} onClick={() => choose('confirm')}>Подтвердить вручную</button>
          <button disabled={isClosed} onClick={() => choose('exempt')}>Освободить</button>
          <button onClick={() => document.getElementById('review-attempt-history')?.scrollIntoView()}>Открыть историю попыток</button>
          <button onClick={() => document.getElementById('review-assignment-history')?.scrollIntoView()}>Открыть историю действий</button>
        </div></details></div>
      {action && <div className="panel review-action-form"><h3>{labels[action]}</h3>
        {action === 'due' && <label>Новый срок<input type="datetime-local" value={due} onChange={event => setDue(event.target.value)} /></label>}
        <label>Причина<textarea value={reason} onChange={event => setReason(event.target.value)} placeholder="Не менее 10 символов" /></label>
        <div><button disabled={busy || reason.trim().length < 10 || (action === 'due' && !due)} onClick={() => void perform()}>Подтвердить</button>
          <button disabled={busy} onClick={() => setAction(null)}>Отмена</button></div></div>}
      <section id="review-attempt-history"><h3>Попытки и ответы</h3>{detail.attempts.length ? detail.attempts.map(row =>
        <div className="review-attempt-row" key={row.id}><b>Попытка № {row.attempt_no}</b><span>{row.status} · {row.correct_count ?? '—'}/{row.auto_count ?? '—'}{row.reward_points ? ` · +${row.reward_points} баллов` : ''}</span>
          <span>{when(row.started_at)}</span>{row.review_id && <button onClick={() => onOpenReview(row.review_id!)}>Открыть ответы</button>}
          <button disabled={isClosed} onClick={() => choose('attempt', row)}>Выдать попытку</button></div>) : <p>Попыток пока нет.</p>}</section>
      <section id="review-assignment-history"><h3>История действий</h3>{detail.history.length ? detail.history.map(row =>
        <div className="review-history-row" key={row.id}><b>{row.action}</b><span>{when(row.occurred_at)}</span><p>{row.reason}</p></div>) : <p>Дополнительных действий пока нет.</p>}</section>
    </>}
  </section>
}
