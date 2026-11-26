import { useState } from 'react'

type Question = { id: string; kind: 'single' | 'multiple' | 'free_text'; prompt: string; required: boolean; image_asset_id: string | null; options: { id: string; text: string; image_asset_id: string | null }[]; answer: Record<string, unknown> | null; correction_required: boolean; review_comment: string | null }
type Attempt = { id: string; attempt_no: number; status: string; deadline_at: string | null; correction_deadline_at: string | null; questions: Question[] }
const api = '/education-next/api'

export default function TestAttemptPanel({ assignmentId, itemId, standaloneTest = false, title, onDone }: {
  assignmentId: string; itemId?: string; standaloneTest?: boolean; title: string; onDone: () => void
}) {
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [answers, setAnswers] = useState<Record<string, { option_ids?: string[]; text?: string }>>({})
  const [outcome, setOutcome] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function begin() {
    setBusy(true); setError(''); setOutcome('')
    try {
      const path = itemId ? `/my/assignments/${assignmentId}/items/${itemId}/attempts`
        : `/my/assignments/${assignmentId}/${standaloneTest ? 'test' : 'revision'}/attempts`
      const response = await fetch(`${api}${path}`, { method: 'POST', credentials: 'include' })
      if (!response.ok) throw new Error(response.status === 409 ? 'Попытки закончились или тест пока недоступен.' : `Не удалось начать тест (${response.status}).`)
      const data = await response.json() as Attempt
      setAttempt(data)
      setAnswers(Object.fromEntries(data.questions.map(question => [question.id, (question.answer ?? {}) as { option_ids?: string[]; text?: string }])))
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  function select(question: Question, optionId: string, checked: boolean) {
    const previous = answers[question.id]?.option_ids ?? []
    setAnswers(current => ({ ...current, [question.id]: { option_ids: question.kind === 'single' ? [optionId]
      : checked ? [...previous, optionId] : previous.filter(id => id !== optionId) } }))
  }

  async function submit() {
    if (!attempt || !window.confirm(attempt.status === 'returned' ? 'Отправить исправленные ответы преподавателю?' : 'Отправить ответы на проверку?')) return
    setBusy(true); setError('')
    try {
      const correcting = attempt.status === 'returned'
      const corrections = Object.fromEntries(attempt.questions.filter(question => question.correction_required)
        .map(question => [question.id, answers[question.id]?.text ?? '']))
      const response = await fetch(`${api}/my/attempts/${attempt.id}/${correcting ? 'correct' : 'submit'}`, { method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers: correcting ? corrections : answers }) })
      if (!response.ok) throw new Error(response.status === 409 ? 'Время или состояние попытки изменилось. Обновите назначение.' : `Не удалось отправить ответы (${response.status}).`)
      const result = await response.json() as { status: string; correct_count: number | null; auto_count: number | null }
      setAttempt(null)
      setOutcome(result.status === 'passed' ? 'Тест сдан.' : result.status === 'pending_review' ? 'Ответы отправлены. Ожидается проверка преподавателя.' : 'Тест не сдан.')
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return <div className="test-attempt">
    <h2>{title}</h2>
    {error && <div className="error" role="alert">{error}</div>}
    {outcome && <div className="panel"><p>{outcome}</p><button onClick={onDone}>{itemId ? 'К программе курса' : 'К обновлению'}</button>{outcome === 'Тест не сдан.' && <button onClick={begin}>Новая попытка</button>}</div>}
    {!attempt && !outcome && <div className="panel"><p>Вопросы и время попытки фиксируются в момент начала. Закрытие вкладки не сбрасывает таймер.</p><button className="primary" disabled={busy} onClick={begin}>Начать тест</button></div>}
    {attempt && <><p>Попытка № {attempt.attempt_no}{attempt.status === 'returned' && attempt.correction_deadline_at ? ` · Исправить до ${new Date(attempt.correction_deadline_at).toLocaleString('ru-RU')}` : attempt.deadline_at ? ` · До ${new Date(attempt.deadline_at).toLocaleString('ru-RU')}` : ''}</p>{attempt.questions.map((question, index) => <section className="panel" key={question.id}><h3>{index + 1}. {question.prompt}</h3>{question.image_asset_id && <img className="test-image" src={`${api}/media/${question.image_asset_id}`} alt={`Изображение вопроса ${index + 1}`} />}{question.review_comment && <p className="review-comment">Комментарий преподавателя: {question.review_comment}</p>}{question.kind === 'free_text' ? <textarea aria-label={`Ответ на вопрос ${index + 1}`} disabled={attempt.status === 'returned' && !question.correction_required} value={answers[question.id]?.text ?? ''} onChange={e => setAnswers(current => ({ ...current, [question.id]: { text: e.target.value } }))} /> : question.options.map(option => <label key={option.id}><input disabled={attempt.status === 'returned'} type={question.kind === 'single' ? 'radio' : 'checkbox'} name={question.id} checked={(answers[question.id]?.option_ids ?? []).includes(option.id)} onChange={e => select(question, option.id, e.target.checked)} /> {option.text}{option.image_asset_id && <img className="test-image" src={`${api}/media/${option.image_asset_id}`} alt="Изображение варианта ответа" />}</label>)}</section>)}<button className="primary" disabled={busy} onClick={submit}>{busy ? 'Отправляем…' : attempt.status === 'returned' ? 'Отправить исправления' : 'Отправить ответы'}</button></>}
  </div>
}
