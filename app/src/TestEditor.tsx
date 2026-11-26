import { useCallback, useEffect, useRef, useState } from 'react'

type Option = { id?: string; text: string; correct: boolean; image_asset_id?: string | null }
type Question = { id?: string; kind: 'single' | 'multiple' | 'free_text'; prompt: string; required: boolean; image_asset_id?: string | null; options: Option[] }
type Test = { id: string; title: string; summary: string; time_limit_minutes: number | null; max_attempts: number; min_correct: number; reward_points: number; correction_days: number; shuffle_questions: boolean; shuffle_options: boolean; show_results: boolean; row_version: number; questions: Question[] }
const api = '/education-next/api'

function TestImageInput({ value, onChange, label }: { value?: string | null; onChange: (id: string | null) => void; label: string }) {
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  async function upload(file?: File) {
    if (!file) return
    setUploading(true); setError('')
    try {
      const body = new FormData()
      body.append('kind', 'image')
      body.append('file', file)
      const response = await fetch(`${api}/admin/media/upload`, { method: 'POST', credentials: 'include', body })
      if (!response.ok) throw new Error(`Не удалось загрузить изображение (${response.status}).`)
      const asset = await response.json() as { id: string }
      onChange(asset.id)
    } catch (cause) { setError((cause as Error).message) } finally { setUploading(false) }
  }
  return <div className="test-image-input">
    {value && <><img src={`${api}/media/${value}`} alt={label} /><button type="button" onClick={() => onChange(null)}>Убрать изображение</button></>}
    <label>{value ? 'Заменить изображение' : 'Добавить изображение'}<input type="file" accept=".png,.jpg,.jpeg,.webp" disabled={uploading} onChange={event => { void upload(event.target.files?.[0]); event.target.value = '' }} /></label>
    {uploading && <span>Загружаем…</span>}{error && <span role="alert">{error}</span>}
  </div>
}

export default function TestEditor({ testId, onBack, backLabel = 'К программе курса' }: { testId: string; onBack: () => void; backLabel?: string }) {
  const [test, setTest] = useState<Test | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [preview, setPreview] = useState(false)
  const editSeq = useRef(0)

  useEffect(() => {
    let active = true
    fetch(`${api}/admin/tests/${testId}`, { credentials: 'include' })
      .then(async response => { if (!response.ok) throw new Error(`Не удалось открыть тест (${response.status}).`); return response.json() as Promise<Test> })
      .then(data => { if (active) setTest(data) }).catch(e => { if (active) setError((e as Error).message) })
    return () => { active = false }
  }, [testId])
  useEffect(() => {
    if (!dirty) return
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault() }
    window.addEventListener('beforeunload', protect)
    return () => window.removeEventListener('beforeunload', protect)
  }, [dirty])

  function update(change: Partial<Test>) { if (test) { editSeq.current++; setTest({ ...test, ...change }); setDirty(true); setNotice(''); setError('') } }
  function updateQuestion(index: number, change: Partial<Question>) {
    if (!test) return
    update({ questions: test.questions.map((row, position) => position === index ? { ...row, ...change } : row) })
  }
  function updateOption(questionIndex: number, optionIndex: number, change: Partial<Option>) {
    if (!test) return
    const question = test.questions[questionIndex]
    updateQuestion(questionIndex, { options: question.options.map((row, position) => position === optionIndex ? { ...row, ...change } : row) })
  }
  function moveQuestion(index: number, direction: -1 | 1) {
    if (!test) return
    const questions = [...test.questions]
    const destination = index + direction
    if (destination < 0 || destination >= questions.length) return
    ;[questions[index], questions[destination]] = [questions[destination], questions[index]]
    update({ questions })
  }
  function copyQuestion(index: number) {
    if (!test) return
    const source = test.questions[index]
    const copy: Question = { ...source, id: undefined,
      options: source.options.map(option => ({ ...option, id: undefined })) }
    const questions = [...test.questions]
    questions.splice(index + 1, 0, copy)
    update({ questions })
  }
  const save = useCallback(async () => {
    if (!test || busy || !dirty) return
    const savingSeq = editSeq.current
    setBusy(true); setError(''); setNotice('')
    try {
      const response = await fetch(`${api}/admin/tests/${test.id}`, { method: 'PUT', credentials: 'include',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(test) })
      if (!response.ok) throw new Error(response.status === 409 ? 'Тест изменён в другом окне. Обновите страницу.' : `Не удалось сохранить тест (${response.status}).`)
      const saved = await response.json() as Test
      setTest(current => editSeq.current === savingSeq ? saved : current ? { ...current, row_version: saved.row_version } : saved)
      if (editSeq.current === savingSeq) { setDirty(false); setNotice('Сохранено') }
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }, [test, busy, dirty])
  useEffect(() => {
    if (!dirty || busy || error) return
    const timer = setTimeout(() => { void save() }, 1000)
    return () => clearTimeout(timer)
  }, [dirty, busy, error, test, save])
  function back() {
    if (dirty && !window.confirm('Есть несохранённые изменения. Вернуться без сохранения?')) return
    onBack()
  }

  return <>
    <button className="back" onClick={back}>← {backLabel}</button>
    {error && <div role="alert" className="error">{error}</div>}
    {!test && !error && <p>Загружаем тест…</p>}
    {test && <div className="test-editor">
      <div className="heading"><div><h1>{test.title}</h1><p>Конструктор теста · версия {test.row_version} · {busy ? 'Сохраняется…' : error ? 'Ошибка сохранения' : dirty ? 'Не сохранено' : notice || 'Черновик'}</p></div><div className="course-actions"><button onClick={() => setPreview(value => !value)}>{preview ? 'Редактировать' : 'Предпросмотр'}</button><button className="primary" disabled={busy || !dirty} onClick={() => { void save() }}>{busy ? 'Сохраняем…' : 'Сохранить тест'}</button></div></div>
      {preview ? <div className="panel"><h2>Предпросмотр без попытки</h2>{test.questions.map((question, index) => <div className="test-question" key={question.id ?? index}><h3>{index + 1}. {question.prompt || 'Вопрос без текста'}</h3>{question.image_asset_id && <img className="test-image" src={`${api}/media/${question.image_asset_id}`} alt={`Изображение вопроса ${index + 1}`} />}{question.kind === 'free_text' ? <textarea disabled placeholder="Свободный ответ" /> : question.options.map((option, optionIndex) => <label key={option.id ?? optionIndex}><input disabled type={question.kind === 'single' ? 'radio' : 'checkbox'} name={`preview-${index}`} /> {option.text || 'Вариант'}{option.image_asset_id && <img className="test-image" src={`${api}/media/${option.image_asset_id}`} alt={`Изображение варианта ${optionIndex + 1}`} />}</label>)}</div>)}</div> : <>
      <div className="panel"><h2>Основное</h2><label>Название<input value={test.title} onChange={e => update({ title: e.target.value })} /></label><label>Описание<textarea value={test.summary} onChange={e => update({ summary: e.target.value })} /></label></div>
      <div className="panel"><div className="panel-head"><h2>Вопросы</h2><button onClick={() => update({ questions: [...test.questions, { kind: 'single', prompt: '', required: true, options: [{ text: '', correct: true }, { text: '', correct: false }] }] })}>Добавить вопрос</button></div>{test.questions.map((question, index) => <section className="test-question" key={question.id ?? index}><div className="panel-head"><h3>Вопрос {index + 1}</h3><div className="course-actions"><button aria-label={`Поднять вопрос ${index + 1}`} disabled={index === 0} onClick={() => moveQuestion(index, -1)}>↑</button><button aria-label={`Опустить вопрос ${index + 1}`} disabled={index === test.questions.length - 1} onClick={() => moveQuestion(index, 1)}>↓</button><button onClick={() => copyQuestion(index)}>Копировать вопрос</button><button onClick={() => update({ questions: test.questions.filter((_, position) => position !== index) })}>Удалить вопрос</button></div></div><label>Тип<select value={question.kind} onChange={e => { const kind = e.target.value as Question['kind']; updateQuestion(index, { kind, options: kind === 'free_text' ? [] : question.options.length ? question.options : [{ text: '', correct: true }, { text: '', correct: false }] }) }}><option value="single">Один вариант</option><option value="multiple">Несколько вариантов</option><option value="free_text">Свободный текст</option></select></label><label>Формулировка<textarea value={question.prompt} onChange={e => updateQuestion(index, { prompt: e.target.value })} /></label><TestImageInput value={question.image_asset_id} onChange={id => updateQuestion(index, { image_asset_id: id })} label={`Изображение вопроса ${index + 1}`} /><label className="inline-check"><input type="checkbox" checked={question.required} onChange={e => updateQuestion(index, { required: e.target.checked })} /> Обязательный вопрос</label>{question.kind !== 'free_text' && <div><h4>Варианты ответа</h4>{question.options.map((option, optionIndex) => <div className="test-option" key={option.id ?? optionIndex}><input aria-label={`Правильный ответ ${optionIndex + 1}`} type={question.kind === 'single' ? 'radio' : 'checkbox'} name={`correct-${index}`} checked={option.correct} onChange={e => updateQuestion(index, { options: question.options.map((row, position) => ({ ...row, correct: question.kind === 'single' ? position === optionIndex : position === optionIndex ? e.target.checked : row.correct })) })} /><input aria-label={`Вариант ${optionIndex + 1}`} value={option.text} onChange={e => updateOption(index, optionIndex, { text: e.target.value })} /><TestImageInput value={option.image_asset_id} onChange={id => updateOption(index, optionIndex, { image_asset_id: id })} label={`Изображение варианта ${optionIndex + 1}`} /><button onClick={() => updateQuestion(index, { options: question.options.filter((_, position) => position !== optionIndex) })}>Удалить</button></div>)}<button onClick={() => updateQuestion(index, { options: [...question.options, { text: '', correct: false }] })}>Добавить вариант</button></div>}</section>)}{test.questions.length === 0 && <p>Добавьте первый вопрос.</p>}</div>
      <div className="panel"><h2>Настройки прохождения</h2><label>Минут на попытку<input type="number" min="1" max="1440" placeholder="Без ограничения" value={test.time_limit_minutes ?? ''} onChange={e => update({ time_limit_minutes: e.target.value ? Number(e.target.value) : null })} /></label><label>Полных попыток<input type="number" min="1" max="100" value={test.max_attempts} onChange={e => update({ max_attempts: Number(e.target.value) })} /></label><label>Нужно правильных автоматических ответов<input type="number" min="0" value={test.min_correct} onChange={e => update({ min_correct: Number(e.target.value) })} /></label><label>Дней на исправление свободного ответа<input type="number" min="1" max="365" value={test.correction_days} onChange={e => update({ correction_days: Number(e.target.value) })} /></label><label>Баллов за сданный тест<input type="number" min="0" max="1000000" value={test.reward_points} onChange={e => update({ reward_points: Number(e.target.value) })} /></label><label className="inline-check"><input type="checkbox" checked={test.shuffle_questions} onChange={e => update({ shuffle_questions: e.target.checked })} /> Перемешивать вопросы</label><label className="inline-check"><input type="checkbox" checked={test.shuffle_options} onChange={e => update({ shuffle_options: e.target.checked })} /> Перемешивать варианты</label><label className="inline-check"><input type="checkbox" checked={test.show_results} onChange={e => update({ show_results: e.target.checked })} /> Показывать результат</label></div>
      </>}
    </div>}
  </>
}
