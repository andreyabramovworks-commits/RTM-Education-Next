import { useCallback, useEffect, useRef, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { TableKit } from '@tiptap/extension-table'
import { MediaEmbed } from './MediaEmbedNode'
import { googleEmbedNodes } from './GoogleEmbedNode'

type Folder = { id: string; parent_id: string | null; title: string; description: string }
export type Article = { id: string; folder_id?: string; title: string; summary: string; body: Record<string, unknown>; row_version: number; updated_at?: string }
type Catalog = { folders: Folder[]; articles: Article[] }
type Department = { id: number; parent_id: number | null; title: string }
type MovePreview = { gained: { bitrix_id: number; name: string; article_count: number }[]; lost: { bitrix_id: number; name: string; article_count: number }[]; affected_article_count: number }
type GoogleSource = { article_id: string; article_title: string; file_id: string; source_url: string; source_kind: 'google_document' | 'google_spreadsheet' }
const base = '/education-next/api'

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) throw new Error(response.status === 409 ? 'Статья изменилась в другом окне. Обновите страницу.' : `Не удалось выполнить действие (${response.status}).`)
  return response.json() as Promise<T>
}

export function ArticleView({ article, editable, onSave, onDirtyChange, sourceMode }: {
  article: Article; editable: boolean; onSave: (article: Article, body: Record<string, unknown>) => Promise<void>;
  onDirtyChange?: (dirty: boolean) => void; sourceMode?: 'knowledge' | 'course'
}) {
  const [title, setTitle] = useState(article.title)
  const [summary, setSummary] = useState(article.summary)
  const [busy, setBusy] = useState(false)
  const [mediaError, setMediaError] = useState('')
  const [googleSources, setGoogleSources] = useState<GoogleSource[]>([])
  const [selectedGoogle, setSelectedGoogle] = useState('')
  const [saveError, setSaveError] = useState('')
  const [draftSeq, setDraftSeq] = useState(0)
  const [savedSeq, setSavedSeq] = useState(0)
  const draftSeqRef = useRef(0)
  const savingRef = useRef(false)
  const videoInput = useRef<HTMLInputElement>(null)
  const audioInput = useRef<HTMLInputElement>(null)
  function markDirty() {
    draftSeqRef.current += 1
    setDraftSeq(draftSeqRef.current)
    setSaveError('')
  }
  const editor = useEditor({ extensions: [StarterKit, TableKit, MediaEmbed, ...googleEmbedNodes(article.id)], content: article.body,
    editable, immediatelyRender: false, onUpdate: () => { if (editable) markDirty() } })

  useEffect(() => {
    if (sourceMode !== 'course' || !editable) return
    let active = true
    fetch(`${base}/google/admin/sources`, { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error('Не удалось получить документы Базы знаний.')
        return response.json() as Promise<GoogleSource[]>
      })
      .then(value => { if (active) setGoogleSources(value) })
      .catch(cause => { if (active) setMediaError((cause as Error).message) })
    return () => { active = false }
  }, [sourceMode, editable])

  const saveDraft = useCallback(async () => {
    if (!editor || savingRef.current || draftSeqRef.current === savedSeq) return
    savingRef.current = true; setBusy(true); setSaveError('')
    const savingSeq = draftSeqRef.current
    try {
      await onSave({ ...article, title, summary }, editor.getJSON())
      setSavedSeq(savingSeq)
    } catch (e) { setSaveError((e as Error).message || 'Не удалось сохранить черновик.') }
    finally { savingRef.current = false; setBusy(false) }
  }, [editor, onSave, article, title, summary, savedSeq])

  useEffect(() => {
    if (!editable || draftSeq <= savedSeq || busy || saveError) return
    const timer = setTimeout(() => { void saveDraft() }, 1000)
    return () => clearTimeout(timer)
  }, [editable, draftSeq, savedSeq, busy, saveError, saveDraft])

  useEffect(() => {
    if (!editable || draftSeq <= savedSeq) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault() }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [editable, draftSeq, savedSeq])

  useEffect(() => { onDirtyChange?.(editable && draftSeq > savedSeq) }, [editable, draftSeq, savedSeq, onDirtyChange])

  async function addFile(file: File | undefined, kind: 'video' | 'audio') {
    if (!file || !editor) return
    setBusy(true); setMediaError('')
    try {
      const body = new FormData(); body.append('kind', kind); body.append('file', file)
      const response = await fetch(`${base}/admin/media/upload`, { method: 'POST', credentials: 'include', body })
      if (!response.ok) throw new Error(response.status === 413 ? 'Файл слишком большой.' : 'Не удалось загрузить файл. Проверьте формат.')
      const asset = await response.json() as { id: string }
      editor.chain().focus().insertContent({ type: 'mediaEmbed', attrs: { assetId: asset.id, caption: '' } }).run()
    } catch (e) { setMediaError((e as Error).message) } finally { setBusy(false) }
  }

  async function addRutube() {
    if (!editor) return
    const url = window.prompt('Ссылка на видео RUTUBE')?.trim()
    if (!url) return
    setBusy(true); setMediaError('')
    try {
      const response = await fetch(`${base}/admin/media/rutube`, { method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, title: 'Видео RUTUBE' }) })
      if (!response.ok) throw new Error('Не удалось добавить видео. Проверьте ссылку RUTUBE.')
      const asset = await response.json() as { id: string }
      editor.chain().focus().insertContent({ type: 'mediaEmbed', attrs: { assetId: asset.id, caption: '' } }).run()
    } catch (e) { setMediaError((e as Error).message) } finally { setBusy(false) }
  }
  async function addGoogleDocument() {
    if (!editor || sourceMode !== 'knowledge') return
    const url = window.prompt('Ссылка на Google Документ')?.trim()
    if (!url) return
    const match = /^https:\/\/docs\.google\.com\/document\/d\/([A-Za-z0-9_-]{8,200})(?:\/|$)/.exec(url)
    if (!match) { setMediaError('Укажите ссылку на Google Документ.'); return }
    setMediaError('')
    try {
      const response = await fetch(`${base}/google/admin/documents/${match[1]}/verify`, { credentials: 'include' })
      if (!response.ok) throw new Error('Серверу не удалось прочитать Google Документ. Проверьте доступ к нему.')
      editor.chain().focus().insertContent({ type: 'google_document', attrs: {
        fileId: match[1], sourceUrl: `https://docs.google.com/document/d/${match[1]}/edit`,
      } }).run()
    } catch (cause) { setMediaError((cause as Error).message) }
  }
  function insertSelectedGoogle() {
    const source = googleSources.find(value => `${value.article_id}:${value.file_id}` === selectedGoogle)
    if (source && editor) editor.chain().focus().insertContent({ type: source.source_kind, attrs: {
      fileId: source.file_id, sourceUrl: source.source_url,
    } }).run()
  }
  return <div className="article-page">
    {editable ? <><label>Название статьи<input value={title} onChange={e => { setTitle(e.target.value); markDirty() }} /></label><label>Краткое описание<textarea value={summary} onChange={e => { setSummary(e.target.value); markDirty() }} /></label></> : <><h1>{article.title}</h1>{article.summary && <p>{article.summary}</p>}</>}
    {editable && <div className="editor-toolbar" aria-label="Форматирование статьи">
      <button type="button" onClick={() => editor?.chain().focus().toggleBold().run()}>Жирный</button>
      <button type="button" onClick={() => editor?.chain().focus().toggleItalic().run()}>Курсив</button>
      <button type="button" onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}>Заголовок</button>
      <button type="button" onClick={() => editor?.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()}>Таблица</button>
      <button type="button" onClick={() => editor?.chain().focus().addRowAfter().run()}>Строка +</button>
      <button type="button" onClick={() => editor?.chain().focus().addColumnAfter().run()}>Столбец +</button>
      <button type="button" disabled={busy} onClick={addRutube}>RUTUBE</button>
      {sourceMode === 'knowledge' && <button type="button" disabled={busy} onClick={() => void addGoogleDocument()}>Google Документ</button>}
      {sourceMode === 'course' && <><select aria-label="Документ из Базы знаний" value={selectedGoogle} onChange={event => setSelectedGoogle(event.target.value)}><option value="">Документ из Базы знаний</option>{googleSources.map(source => <option key={`${source.article_id}:${source.file_id}`} value={`${source.article_id}:${source.file_id}`}>{source.article_title}{source.source_kind === 'google_spreadsheet' ? ' · таблица' : ''}</option>)}</select><button type="button" disabled={!selectedGoogle} onClick={insertSelectedGoogle}>Вставить документ</button></>}
      <button type="button" disabled={busy} onClick={() => videoInput.current?.click()}>Загрузить видео</button>
      <button type="button" disabled={busy} onClick={() => audioInput.current?.click()}>Загрузить аудио</button>
    </div>}
    {editable && <><input ref={videoInput} hidden type="file" accept=".mp4,.webm,.mov" onChange={event => { void addFile(event.target.files?.[0], 'video'); event.target.value = '' }} /><input ref={audioInput} hidden type="file" accept=".mp3,.wav" onChange={event => { void addFile(event.target.files?.[0], 'audio'); event.target.value = '' }} /></>}
    {mediaError && <div role="alert" className="error">{mediaError}</div>}
    {saveError && <div role="alert" className="error">Автосохранение не удалось: {saveError}</div>}
    <EditorContent editor={editor} className="article-editor" />
    {editable && <div className="course-actions"><span role="status">{busy ? 'Сохраняется…' : saveError ? 'Ошибка сохранения' : draftSeq > savedSeq ? 'Не сохранено' : 'Сохранено'}</span><button className="primary" disabled={busy || !editor || draftSeq <= savedSeq} onClick={() => { void saveDraft() }}>Сохранить статью</button></div>}
  </div>
}

export default function KnowledgePanel({ mode, role }: { mode: 'admin' | 'user'; role: string }) {
  const [catalog, setCatalog] = useState<Catalog>({ folders: [], articles: [] })
  const [folderId, setFolderId] = useState('')
  const [articleId, setArticleId] = useState('')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [departments, setDepartments] = useState<Department[]>([])
  const [grantTarget, setGrantTarget] = useState<{ type: 'folder' | 'article'; id: string } | null>(null)
  const [subjectType, setSubjectType] = useState<'employee' | 'department' | 'subdepartment'>('employee')
  const [subjectId, setSubjectId] = useState('')
  const [moveTarget, setMoveTarget] = useState<{ type: 'folder' | 'article'; id: string } | null>(null)
  const [destinationId, setDestinationId] = useState('')
  const [movePreview, setMovePreview] = useState<MovePreview | null>(null)
  const [articleDirty, setArticleDirty] = useState(false)
  const [importPreview, setImportPreview] = useState<{ folders: number; articles: number;
    new_folders: number; new_articles: number; external_links: number[];
    warnings: { row: number; reason: string }[] } | null>(null)
  const [importBusy, setImportBusy] = useState(false)
  const canEdit = mode === 'admin' && ['editor', 'admin', 'developer'].includes(role)
  const canManage = mode === 'admin' && ['admin', 'developer'].includes(role)
  const selected = catalog.articles.find(article => article.id === articleId)

  async function reload() {
    const data = await api<Catalog>(mode === 'admin' ? '/admin/knowledge' : '/knowledge')
    setCatalog(data)
    setFolderId(current => current && data.folders.some(folder => folder.id === current) ? current : data.folders[0]?.id ?? '')
  }

  useEffect(() => {
    let mounted = true
    api<Catalog>(mode === 'admin' ? '/admin/knowledge' : '/knowledge').then(data => {
      if (!mounted) return
      setCatalog(data); setFolderId(data.folders[0]?.id ?? '')
    }).catch(e => { if (mounted) setError((e as Error).message) }).finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [mode])

  useEffect(() => {
    if (!canManage) return
    api<Department[]>('/admin/employees/departments').then(setDepartments).catch(e => setError((e as Error).message))
  }, [canManage])

  async function createFolder() {
    const title = window.prompt('Название папки')?.trim()
    if (!title) return
    setError('')
    try {
      const folder = await api<Folder>('/admin/knowledge/folders', { method: 'POST', body: JSON.stringify({ title, parent_id: folderId || null }) })
      await reload(); setFolderId(folder.id)
    } catch (e) { setError((e as Error).message) }
  }

  async function previewImport() {
    setError(''); setImportBusy(true)
    try { setImportPreview(await api('/admin/knowledge/catalog-import/preview')) }
    catch (e) { setError((e as Error).message) }
    finally { setImportBusy(false) }
  }

  async function runImport() {
    if (!importPreview || !window.confirm(`Добавить ${importPreview.new_folders} папок и ${importPreview.new_articles} статей из каталога?`)) return
    setError(''); setImportBusy(true)
    try {
      await api('/admin/knowledge/catalog-import', { method: 'POST', body: JSON.stringify({ confirmed: true }) })
      setImportPreview(null); await reload()
    } catch (e) { setError((e as Error).message) }
    finally { setImportBusy(false) }
  }

  async function createArticle() {
    if (!folderId) { setError('Сначала создайте папку.'); return }
    const title = window.prompt('Название статьи')?.trim()
    if (!title) return
    setError('')
    try {
      const article = await api<Article>('/admin/knowledge/articles', { method: 'POST', body: JSON.stringify({ title, folder_id: folderId }) })
      await reload(); setArticleId(article.id)
    } catch (e) { setError((e as Error).message) }
  }

  async function saveArticle(article: Article, body: Record<string, unknown>) {
    setError('')
    try {
      const saved = await api<Article>(`/admin/knowledge/articles/${article.id}`, { method: 'PUT', body: JSON.stringify({ title: article.title, summary: article.summary, body, row_version: article.row_version }) })
      setCatalog(current => ({ ...current, articles: current.articles.map(row => row.id === saved.id ? saved : row) }))
    } catch (e) { setError((e as Error).message); throw e }
  }

  async function grantAccess() {
    if (!grantTarget || !subjectId.trim()) return
    if (!window.confirm('Открыть доступ выбранным сотрудникам?')) return
    setError('')
    try {
      await api('/admin/knowledge/grants', { method: 'POST', body: JSON.stringify({ target_type: grantTarget.type, target_id: grantTarget.id, subject_type: subjectType, subject_id: subjectId.trim() }) })
      setGrantTarget(null); setSubjectId('')
    } catch (e) { setError((e as Error).message) }
  }

  async function moveSelected() {
    if (!moveTarget || !movePreview || (moveTarget.type === 'article' && !destinationId)) return
    if (!window.confirm(`Переместить? Доступ появится у ${movePreview.gained.length} и пропадёт у ${movePreview.lost.length} сотрудников.`)) return
    setError('')
    try {
      if (moveTarget.type === 'article') {
        await api(`/admin/knowledge/articles/${moveTarget.id}/folder`, { method: 'PUT',
          body: JSON.stringify({ folder_id: destinationId, confirmed: true }) })
        setFolderId(destinationId)
      } else {
        await api(`/admin/knowledge/folders/${moveTarget.id}/parent`, { method: 'PUT',
          body: JSON.stringify({ parent_id: destinationId || null, confirmed: true }) })
      }
      setMoveTarget(null); setMovePreview(null); await reload()
    } catch (e) { setError((e as Error).message) }
  }

  async function previewSelectedMove() {
    if (!moveTarget || (moveTarget.type === 'article' && !destinationId)) return
    setError('')
    try {
      setMovePreview(await api<MovePreview>('/admin/knowledge/move-preview', {
        method: 'POST', body: JSON.stringify({ target_type: moveTarget.type,
          target_id: moveTarget.id, destination_id: destinationId || null }),
      }))
    } catch (e) { setMovePreview(null); setError((e as Error).message) }
  }

  function depth(folder: Folder): number {
    const folders = new Map(catalog.folders.map(row => [row.id, row]))
    let level = 0, parent = folder.parent_id
    while (parent && folders.has(parent) && level < 20) { level++; parent = folders.get(parent)?.parent_id ?? null }
    return level
  }

  return <>
    <div className="crumb">{mode === 'admin' ? 'Рабочее пространство / ' : ''}База знаний</div>
    <div className="heading"><div><h1>База знаний</h1><p>Статьи и папки компании.</p></div>{canManage && <div className="review-actions"><button disabled={importBusy} onClick={previewImport}>Импорт из каталога</button><button className="primary" onClick={createFolder}>Создать папку</button></div>}</div>
    {error && <div role="alert" className="error">{error}</div>}
    {importPreview && <div className="panel" aria-label="Предпросмотр импорта"><h2>Предпросмотр каталога</h2><p>В таблице: {importPreview.folders} папок и {importPreview.articles} статей. Новых: {importPreview.new_folders} папок и {importPreview.new_articles} статей.</p><p>Внешних ссылок: {importPreview.external_links.length}; строк с ошибкой ссылки или вложенности: {importPreview.warnings.length}.</p>{importPreview.warnings.length > 0 && <details><summary>Показать строки с ошибками</summary>{importPreview.warnings.map(item => <p key={item.row}>Строка {item.row}: {item.reason}</p>)}</details>}<div className="review-actions"><button onClick={() => setImportPreview(null)}>Закрыть</button><button className="primary" disabled={importBusy || importPreview.new_articles + importPreview.new_folders === 0} onClick={runImport}>Добавить новые записи</button></div></div>}
    {loading ? <p>Загружаем базу знаний…</p> : <div className="knowledge-layout">
      <aside className="knowledge-tree" aria-label="Папки"><h2>Папки</h2>{catalog.folders.map(folder => <button key={folder.id} className={folderId === folder.id ? 'selected' : ''} style={{ paddingLeft: 14 + depth(folder) * 16 }} onClick={() => { if (articleDirty && !window.confirm('Есть несохранённые изменения. Покинуть статью?')) return; setArticleDirty(false); setFolderId(folder.id); setArticleId('') }}>{folder.title}</button>)}{catalog.folders.length === 0 && <p>Папок пока нет.</p>}{canManage && folderId && <><button className="grant-link" onClick={() => setGrantTarget({ type: 'folder', id: folderId })}>Открыть доступ к папке</button><button className="grant-link" onClick={() => { setMoveTarget({ type: 'folder', id: folderId }); setDestinationId(''); setMovePreview(null) }}>Переместить папку</button></>}</aside>
      <div className="knowledge-content">{selected ? <><button className="back" onClick={() => { if (articleDirty && !window.confirm('Есть несохранённые изменения. Покинуть статью?')) return; setArticleDirty(false); setArticleId('') }}>← К статьям</button><ArticleView key={selected.id} article={selected} editable={canEdit} onSave={saveArticle} onDirtyChange={setArticleDirty} sourceMode={canEdit ? 'knowledge' : undefined} />{canManage && <><button className="grant-link" onClick={() => setGrantTarget({ type: 'article', id: selected.id })}>Открыть доступ к статье</button><button className="grant-link" onClick={() => { setMoveTarget({ type: 'article', id: selected.id }); setDestinationId(''); setMovePreview(null) }}>Переместить статью</button></>}</> : <><div className="knowledge-actions"><input aria-label="Поиск статей" placeholder="Поиск статей" value={search} onChange={e => setSearch(e.target.value)} />{canEdit && <button className="primary" onClick={createArticle}>Создать статью</button>}</div><div className="table"><table><thead><tr><th>Статья</th><th>Описание</th><th>Изменена</th></tr></thead><tbody>{catalog.articles.filter(article => article.folder_id === folderId && `${article.title} ${article.summary}`.toLocaleLowerCase('ru-RU').includes(search.toLocaleLowerCase('ru-RU'))).map(article => <tr key={article.id} tabIndex={0} onClick={() => setArticleId(article.id)} onKeyDown={e => e.key === 'Enter' && setArticleId(article.id)}><td><b>{article.title}</b></td><td>{article.summary}</td><td>{article.updated_at ? new Date(article.updated_at).toLocaleDateString('ru-RU') : '—'}</td></tr>)}</tbody></table>{catalog.articles.filter(article => article.folder_id === folderId).length === 0 && <div className="empty">В этой папке пока нет статей.</div>}</div></>}</div>
    </div>}
    {grantTarget && <div className="panel grant-panel"><h2>Открыть доступ к {grantTarget.type === 'folder' ? 'папке' : 'статье'}</h2><label>Кому открыть<select value={subjectType} onChange={e => { setSubjectType(e.target.value as typeof subjectType); setSubjectId('') }}><option value="employee">Сотруднику</option><option value="department">Только сотрудникам отдела</option><option value="subdepartment">Отделу и всем подотделам</option></select></label>{subjectType === 'employee' ? <label>ID сотрудника в Битрикс24<input value={subjectId} onChange={e => setSubjectId(e.target.value)} inputMode="numeric" /></label> : <label>Подразделение<select value={subjectId} onChange={e => setSubjectId(e.target.value)}><option value="">Выберите подразделение</option>{departments.map(department => <option key={department.id} value={department.id}>{department.title} · ID {department.id}</option>)}</select></label>}<div className="review-actions"><button onClick={() => setGrantTarget(null)}>Отмена</button><button className="primary" disabled={!subjectId.trim()} onClick={grantAccess}>Открыть доступ</button></div></div>}
    {moveTarget && <div className="panel grant-panel"><h2>Переместить {moveTarget.type === 'folder' ? 'папку' : 'статью'}</h2><p>Перед перемещением проверьте, у кого изменится доступ.</p><label>Новая папка<select value={destinationId} onChange={e => { setDestinationId(e.target.value); setMovePreview(null) }}><option value="">{moveTarget.type === 'folder' ? 'В корень Базы знаний' : 'Выберите папку'}</option>{catalog.folders.filter(folder => folder.id !== moveTarget.id).map(folder => <option key={folder.id} value={folder.id}>{folder.title}</option>)}</select></label>{movePreview && <div className="panel"><p>Затронутых статей: {movePreview.affected_article_count}</p><p>Получат доступ: {movePreview.gained.length}. Потеряют доступ: {movePreview.lost.length}.</p>{movePreview.gained.map(person => <p key={`gain-${person.bitrix_id}`}>+ {person.name} · {person.article_count} ст.</p>)}{movePreview.lost.map(person => <p key={`loss-${person.bitrix_id}`}>− {person.name} · {person.article_count} ст.</p>)}</div>}<div className="review-actions"><button onClick={() => { setMoveTarget(null); setMovePreview(null) }}>Отмена</button><button disabled={moveTarget.type === 'article' && !destinationId} onClick={previewSelectedMove}>Проверить доступ</button><button className="primary" disabled={!movePreview} onClick={moveSelected}>Переместить</button></div></div>}
  </>
}
