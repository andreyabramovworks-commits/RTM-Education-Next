import { useEffect, useState } from 'react'

type QueueRow = { id: string; status: string; learner_name: string; campaign_title: string; test_title: string; created_at: string }
type Question = { id: string; kind: string; prompt: string; image_asset_id: string | null; options: { id: string; text: string; image_asset_id: string | null }[]; correct_option_ids: string[]; submissions: { id: string; version: number; value: { text?: string; option_ids?: string[] }; is_correct: boolean | null; reviews: { decision: string; comment: string; created_at: string }[] }[] }
type Review = { id: string; status: string; row_version: number; assignment_id: string; course_item_id: string | null; target_type: string; learner_name: string; campaign_title: string; test_title: string; claimed_by: string | null; questions: Question[]; draft: Record<string, { decision: string; comment: string }> }
const base = '/education-next/api/admin'

function QuestionReview({ question, number, editable, decision, onDecision }: {
  question: Question; number: number; editable: boolean; decision?: { decision: string; comment: string };
  onDecision: (value: { decision: string; comment: string }) => void
}) {
  const latest = question.submissions.at(-1)
  const selected = new Set(latest?.value.option_ids ?? [])
  const correct = new Set(question.correct_option_ids)
  return <section className="panel review-question">
    <h2>{number}. {question.prompt}</h2>
    {question.image_asset_id && <img className="test-image" src={`/education-next/api/media/${question.image_asset_id}`} alt={`Изображение вопроса ${number}`} />}
    {question.kind !== 'free_text' ? <>
      <div className="review-options">{question.options.map(option => <div key={option.id}>
        <span>{selected.has(option.id) ? 'Выбран · ' : ''}{correct.has(option.id) ? 'Верный ответ · ' : ''}{option.text}</span>
        {option.image_asset_id && <img className="test-image" src={`/education-next/api/media/${option.image_asset_id}`} alt="Изображение варианта ответа" />}
      </div>)}</div>
      <p>{latest?.is_correct ? 'Ответ верный' : 'Ответ неверный'}</p>
    </> : <>
      {question.submissions.map(submission => <div className="review-answer-version" key={submission.id}>
        <small>Ответ · версия {submission.version}</small>
        <p>{submission.value.text || 'Ответ не заполнен'}</p>
        {submission.reviews.map((review, index) => <p key={index}>
          {review.decision === 'accepted' ? 'Принят' : 'Возвращён'} · {new Date(review.created_at).toLocaleString('ru-RU')}
          {review.comment && ` · ${review.comment}`}
        </p>)}
      </div>)}
      {editable && <><div className="review-decisions">
        <button className={decision?.decision === 'accepted' ? 'chosen' : ''} onClick={() => onDecision({ decision: 'accepted', comment: decision?.comment || '' })}>Принять</button>
        <button className={decision?.decision === 'rejected' ? 'chosen' : ''} onClick={() => onDecision({ decision: 'rejected', comment: decision?.comment || '' })}>Вернуть</button>
      </div>{decision?.decision === 'rejected' && <label>Комментарий сотруднику<textarea value={decision.comment} onChange={e => onDecision({ ...decision, comment: e.target.value })} /></label>}</>}
    </>}
  </section>
}

async function call<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({})) as { detail?: string }
    throw new Error(detail.detail || `Ошибка ${response.status}`)
  }
  return response.json() as Promise<T>
}

export default function ReviewPanel() {
  const [context, setContext] = useState<'actions' | 'courses' | 'materials'>('courses')
  const [rows, setRows] = useState<QueueRow[]>([])
  const [selected, setSelected] = useState<Review | null>(null)
  const [draft, setDraft] = useState<Record<string, { decision: string; comment: string }>>({})
  const [returnMode, setReturnMode] = useState<'full_retake' | 'answer_correction'>('answer_correction')
  const [allowanceReason, setAllowanceReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (context === 'actions') return
    call<QueueRow[]>(`/reviews?context=${context}`).then(setRows).catch(e => setError((e as Error).message))
  }, [context])

  async function open(id: string) {
    setError('')
    try { const value = await call<Review>(`/reviews/${id}`); setSelected(value); setDraft(value.draft || {}) }
    catch (e) { setError((e as Error).message) }
  }

  async function claim() {
    if (!selected) return
    setBusy(true); setError('')
    try { setSelected(await call<Review>(`/reviews/${selected.id}/claim`, { method: 'POST' })) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function save() {
    if (!selected) return
    setBusy(true); setError('')
    try { setSelected(await call<Review>(`/reviews/${selected.id}/draft`, { method: 'PUT', body: JSON.stringify({ row_version: selected.row_version, decisions: draft }) })) }
    catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function complete() {
    if (!selected || !window.confirm('Завершить проверку? Решение будет зафиксировано в истории.')) return
    setBusy(true); setError('')
    try {
      const result = await call<Review>(`/reviews/${selected.id}/complete`, { method: 'POST', body: JSON.stringify({ row_version: selected.row_version, return_mode: returnMode, confirmed: true }) })
      setSelected(result)
      setRows(current => current.filter(row => row.id !== result.id))
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function grantAttempt() {
    if (!selected || !window.confirm('Выдать сотруднику одну дополнительную попытку?')) return
    setBusy(true); setError('')
    try {
      const path = selected.course_item_id
        ? `/assignments/${selected.assignment_id}/items/${selected.course_item_id}/attempt-allowances`
        : `/assignments/${selected.assignment_id}/${selected.target_type === 'course_test' ? 'test' : 'revision'}/attempt-allowances`
      await call(path, {
        method: 'POST', body: JSON.stringify({ delta: 1, reason: allowanceReason, confirmed: true }),
      })
      setAllowanceReason('')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const free = selected?.questions.filter(q => q.kind === 'free_text') || []
  const rejected = free.some(q => draft[q.id]?.decision === 'rejected')
  return <div className="review-panel">
    <div className="crumb">Рабочее пространство / Центр проверок</div>
    <div className="heading"><div><h1>Центр проверок</h1><p>Свободные ответы сотрудников, ожидающие решения преподавателя.</p></div></div>
    {error && <div className="error" role="alert">{error}</div>}
    <div className="tabs"><button className={context === 'actions' ? 'active' : ''} onClick={() => { setContext('actions'); setSelected(null) }}>Требует действий</button><button className={context === 'materials' ? 'active' : ''} onClick={() => { setContext('materials'); setSelected(null) }}>Проверка отдельных материалов</button><button className={context === 'courses' ? 'active' : ''} onClick={() => { setContext('courses'); setSelected(null) }}>Проверка курсов обучений</button></div>
    {context === 'actions' ? <div className="panel"><h2>Требует действий</h2><p>Личная очередь преподавателя появится в следующем выпуске.</p></div> : !selected ? <div className="table"><table><thead><tr><th>Сотрудник</th><th>Назначение</th><th>Тест</th><th>Статус</th><th>Поступило</th></tr></thead><tbody>{rows.map(row => <tr key={row.id} tabIndex={0} onClick={() => open(row.id)} onKeyDown={e => { if (e.key === 'Enter') open(row.id) }}><td>{row.learner_name}</td><td>{row.campaign_title}</td><td>{row.test_title}</td><td>{row.status === 'claimed' ? 'В работе' : 'Ожидает'}</td><td>{new Date(row.created_at).toLocaleString('ru-RU')}</td></tr>)}</tbody></table>{rows.length === 0 && <div className="empty">Новых ответов нет.</div>}</div> : <>
      <button className="back" onClick={() => setSelected(null)}>← К списку</button>
      <div className="heading"><div><h1>{selected.learner_name}</h1><p>{selected.campaign_title} · {selected.test_title}</p></div>{selected.status === 'pending' && <button className="primary" disabled={busy} onClick={claim}>Взять в работу</button>}</div>
      {selected.status === 'claimed' && <div className="review-questions">{selected.questions.map((question, index) => <QuestionReview key={question.id} question={question} number={index + 1} editable={question.kind === 'free_text'} decision={draft[question.id]} onDecision={value => setDraft(current => ({ ...current, [question.id]: value }))} />)}
        {rejected && <div className="panel"><h2>Что вернуть сотруднику</h2><label><input type="radio" checked={returnMode === 'answer_correction'} onChange={() => setReturnMode('answer_correction')} /> Исправить только отклонённые ответы в этой попытке</label><label><input type="radio" checked={returnMode === 'full_retake'} onChange={() => setReturnMode('full_retake')} /> Пройти тест заново</label>{returnMode === 'full_retake' && <div className="allowance"><p>Если лимит попыток исчерпан, укажите причину и выдайте одну дополнительную попытку перед возвратом.</p><input aria-label="Причина дополнительной попытки" value={allowanceReason} onChange={e => setAllowanceReason(e.target.value)} placeholder="Причина дополнительной попытки" /><button disabled={busy || allowanceReason.trim().length < 10} onClick={grantAttempt}>Выдать попытку</button></div>}</div>}
        <div className="review-actions"><button disabled={busy} onClick={save}>Сохранить решения</button><button className="primary" disabled={busy || JSON.stringify(draft) !== JSON.stringify(selected.draft)} onClick={complete}>Завершить проверку</button></div>
      </div>}
      {selected.status === 'completed' && <div className="panel">Проверка завершена.</div>}
    </>}
  </div>
}
