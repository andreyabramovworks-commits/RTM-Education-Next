import { useEffect, useState } from 'react'
import { ArticleView, type Article } from './KnowledgePanel'

const api = '/education-next/api'

export default function CourseArticleEditor({ courseId, articleId, canEdit, onBack }: {
  courseId: string; articleId: string; canEdit: boolean; onBack: () => void
}) {
  const [article, setArticle] = useState<Article | null>(null)
  const [error, setError] = useState('')
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    let active = true
    fetch(`${api}/admin/courses/${courseId}/articles/${articleId}`, { credentials: 'include' })
      .then(async response => { if (!response.ok) throw new Error(`Не удалось открыть статью (${response.status}).`); return response.json() as Promise<Article> })
      .then(data => { if (active) setArticle(data) })
      .catch(e => { if (active) setError((e as Error).message) })
    return () => { active = false }
  }, [courseId, articleId])

  async function save(next: Article, body: Record<string, unknown>) {
    setError('')
    const response = await fetch(`${api}/admin/courses/${courseId}/articles/${articleId}`, {
      method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: next.title, summary: next.summary, body, row_version: next.row_version }),
    })
    if (!response.ok) {
      const message = response.status === 409 ? 'Статья изменилась в другом окне. Обновите страницу.' : `Не удалось сохранить статью (${response.status}).`
      setError(message)
      throw new Error(message)
    }
    setArticle(await response.json() as Article)
  }

  return <>
    <button className="back" onClick={() => { if (!dirty || window.confirm('Есть несохранённые изменения. Покинуть статью?')) onBack() }}>← К программе курса</button>
    {error && <div role="alert" className="error">{error}</div>}
    {!article && !error && <p>Загружаем статью…</p>}
    {article && <ArticleView article={article} editable={canEdit} onSave={save} onDirtyChange={setDirty} sourceMode={canEdit ? 'course' : undefined} />}
  </>
}
