import { useEffect, useState } from 'react'
import { ArticleView, type Article } from './KnowledgePanel'

type Item = { id: string; kind: 'article' | 'test'; article_id: string | null; test_id: string | null;
  title: string; position: number; required: boolean }
type Section = { id: string; title: string; position: number; items?: Item[] }
type Course = { id: string; title: string; description: string; mode: 'free' | 'sequential'; sections?: Section[] }
type Question = { id: string; kind: 'single' | 'multiple' | 'free_text'; prompt: string;
  image_asset_id?: string | null; options: { id: string; text: string; image_asset_id?: string | null }[] }
type PreviewTest = { id: string; title: string; summary: string; questions: Question[];
  time_limit_minutes: number | null; max_attempts: number; min_correct: number }
const api = '/education-next/api'

export default function CoursePreview({ course, onBack, onEditItem }: {
  course: Course; onBack: () => void; onEditItem: (item: Item) => void
}) {
  const [selected, setSelected] = useState<Item | null>(null)
  const [completed, setCompleted] = useState<Set<string>>(() => new Set())
  const [article, setArticle] = useState<Article | null>(null)
  const [test, setTest] = useState<PreviewTest | null>(null)
  const [error, setError] = useState('')
  const sections = [...(course.sections ?? [])].sort((a, b) => a.position - b.position)
  const locked = new Set<string>()
  let requiredIncomplete = false
  for (const section of sections) {
    for (const item of [...(section.items ?? [])].sort((a, b) => a.position - b.position)) {
      if (course.mode === 'sequential' && requiredIncomplete && !completed.has(item.id)) locked.add(item.id)
      if (item.required && !completed.has(item.id)) requiredIncomplete = true
    }
  }

  useEffect(() => {
    if (!selected) return
    let active = true
    const path = selected.kind === 'article' && selected.article_id
      ? `/admin/courses/${course.id}/articles/${selected.article_id}`
      : selected.kind === 'test' && selected.test_id ? `/admin/tests/${selected.test_id}` : null
    if (!path) return
    fetch(`${api}${path}`, { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error(`Не удалось открыть материал (${response.status}).`)
        return response.json() as Promise<Article | PreviewTest>
      })
      .then(value => {
        if (!active) return
        if (selected.kind === 'article') setArticle(value as Article)
        else setTest(value as PreviewTest)
      })
      .catch(cause => { if (active) setError((cause as Error).message) })
    return () => { active = false }
  }, [course.id, selected])

  function open(item: Item) {
    if (locked.has(item.id)) return
    setArticle(null); setTest(null); setError(''); setSelected(item)
  }

  function complete() {
    if (!selected) return
    setCompleted(previous => new Set(previous).add(selected.id))
    setSelected(null); setArticle(null); setTest(null)
  }

  return <>
    <button className="back" onClick={selected ? () => setSelected(null) : onBack}>← {selected ? 'К программе предпросмотра' : 'К редактору курса'}</button>
    <div className="heading"><div><h1>{course.title}</h1><p>Предпросмотр пути ученика · {course.mode === 'sequential' ? 'последовательно' : 'свободно'}</p></div></div>
    <p>Действия здесь только показывают сценарий. Назначения, попытки, баллы и уведомления не создаются.</p>
    {error && <div className="error" role="alert">{error}</div>}
    {selected ? <>
      <div className="course-actions"><button onClick={() => onEditItem(selected)}>Открыть в редакторе</button></div>
      {!article && !test && !error && <p role="status">Загружаем материал…</p>}
      {article && <ArticleView key={article.id} article={article} editable={false} onSave={async () => {}} />}
      {test && <section className="panel"><h2>{test.title}</h2>{test.summary && <p>{test.summary}</p>}
        <p>Время: {test.time_limit_minutes ? `${test.time_limit_minutes} мин.` : 'без ограничения'} · Попыток: {test.max_attempts} · Порог: {test.min_correct} правильных ответов.</p>
        {test.questions.map((question, index) => <div className="test-question" key={question.id}><h3>{index + 1}. {question.prompt}</h3>
          {question.image_asset_id && <img className="test-image" src={`${api}/media/${question.image_asset_id}`} alt={`Изображение вопроса ${index + 1}`} />}
          {question.kind === 'free_text' ? <textarea disabled placeholder="Свободный ответ" /> : question.options.map(option => <label key={option.id}>
            <input disabled type={question.kind === 'single' ? 'radio' : 'checkbox'} name={`course-preview-${question.id}`} /> {option.text}
            {option.image_asset_id && <img className="test-image" src={`${api}/media/${option.image_asset_id}`} alt="Изображение варианта" />}
          </label>)}
        </div>)}
      </section>}
      {(article || test) && <button className="primary" onClick={complete}>Смоделировать завершение</button>}
    </> : <div className="learning-sections">{sections.map(section => <section className="panel" key={section.id}><h2>{section.title}</h2>
      {[...(section.items ?? [])].sort((a, b) => a.position - b.position).map(item => <button className="learning-item" key={item.id}
        disabled={locked.has(item.id)} onClick={() => open(item)}><span>{item.kind === 'article' ? 'Статья' : 'Тест'}</span><b>{item.title}</b>
        <small>{completed.has(item.id) ? 'Завершено в предпросмотре' : locked.has(item.id) ? 'Пока недоступно' : item.required ? 'Обязательно' : 'Необязательно'}</small>
      </button>)}{!section.items?.length && <p>В разделе пока нет материалов.</p>}</section>)}
      {!sections.length && <p>Добавьте раздел и материалы, чтобы увидеть путь ученика.</p>}
    </div>}
  </>
}
