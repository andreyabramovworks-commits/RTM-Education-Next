import { lazy, Suspense, useEffect, useState, type DragEvent } from 'react'
import './App.css'

const KnowledgePanel = lazy(() => import('./KnowledgePanel'))
const RevisionPanel = lazy(() => import('./RevisionPanel'))
const RevisionAssignments = lazy(() => import('./RevisionAssignments'))
const CourseArticleEditor = lazy(() => import('./CourseArticleEditor'))
const LearningPanel = lazy(() => import('./LearningPanel'))
const CampaignWizard = lazy(() => import('./CampaignWizard'))
const TestEditor = lazy(() => import('./TestEditor'))
const ReviewPanel = lazy(() => import('./ReviewPanel'))
const SettingsPanel = lazy(() => import('./SettingsPanel'))
const ProfilePanel = lazy(() => import('./ProfilePanel'))
const CopyMaterialDialog = lazy(() => import('./CopyMaterialDialog'))

type User = { id: string; name: string; role: string }
type CourseItem = { id: string; kind: 'article' | 'test'; article_id: string | null; test_id: string | null; title: string; position: number; required: boolean }
type Section = { id: string; title: string; position: number; items?: CourseItem[] }
type Course = { id: string; title: string; description: string; mode: 'free' | 'sequential'; status: string; row_version: number; updated_at: string; sections?: Section[] }
type Staff = { id: string; bitrix_id: number; name: string; local_role: string; effective_role: string; active: boolean }
type Campaign = { id: string; title: string; status: string; recipient_count: number }
const api = '/education-next/api'
const rank: Record<string, number> = { employee: 0, teacher: 1, editor: 2, admin: 3, developer: 4 }
const roleNames: Record<string, string> = { employee: 'Пользователь', teacher: 'Преподаватель', editor: 'Редактор', admin: 'Администратор', developer: 'Разработчик' }

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${api}${path}`, { credentials: 'include', headers: { 'Content-Type': 'application/json' }, ...options })
  if (!response.ok) {
    if (response.status === 401) throw new Error('Сессия закончилась. Откройте приложение из Битрикс24 заново.')
    if (response.status === 403) throw new Error('Недостаточно прав для этого действия.')
    if (response.status === 409) throw new Error('Курс изменён в другом окне. Обновите страницу перед сохранением.')
    throw new Error(`Не удалось выполнить действие (${response.status}). Попробуйте ещё раз.`)
  }
  return response.json() as Promise<T>
}

export default function CourseApp() {
  const [user, setUser] = useState<User | null>(null)
  const [courses, setCourses] = useState<Course[]>([])
  const [course, setCourse] = useState<Course | null>(null)
  const [courseArticleId, setCourseArticleId] = useState<string | null>(null)
  const [courseTestId, setCourseTestId] = useState<string | null>(null)
  const [copyIntoSection, setCopyIntoSection] = useState<Section | null>(null)
  const [campaignOpen, setCampaignOpen] = useState(false)
  const [materialTarget, setMaterialTarget] = useState<{ type: 'course_article' | 'course_test'; id: string; title: string } | null>(null)
  const [materialCampaigns, setMaterialCampaigns] = useState<Campaign[]>([])
  const [selectedMaterialCampaign, setSelectedMaterialCampaign] = useState<Campaign | null>(null)
  const [selectedCampaign, setSelectedCampaign] = useState<Campaign | null>(null)
  const [courseCampaigns, setCourseCampaigns] = useState<Campaign[]>([])
  const [view, setView] = useState<'user' | 'admin'>('user')
  const [adminTab, setAdminTab] = useState<'courses' | 'revisions' | 'reviews' | 'knowledge' | 'employees' | 'settings'>('courses')
  const [staff, setStaff] = useState<Staff[]>([])
  const [staffHasMore, setStaffHasMore] = useState(false)
  const [staffSearch, setStaffSearch] = useState('')
  const [userTab, setUserTab] = useState<'learning' | 'knowledge' | 'profile'>('learning')
  const [learningTab, setLearningTab] = useState<'courses' | 'updates'>('courses')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    request<User>('/auth/me').then(setUser).catch(e => setError(e.message)).finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    if (!user || rank[user.role] < rank.teacher) return
    request<Course[]>(`/admin/courses?search=${encodeURIComponent(search)}`).then(setCourses).catch(e => setError(e.message))
  }, [user, search])
  useEffect(() => {
    if (!user || view !== 'admin' || adminTab !== 'employees' || rank[user.role] < rank.admin) return
    request<Staff[]>('/admin/employees?limit=100').then(rows => { setStaff(rows); setStaffHasMore(rows.length === 100) }).catch(e => setError(e.message))
  }, [user, view, adminTab])

  async function loadMoreStaff() {
    setSaving(true); setError('')
    try {
      const rows = await request<Staff[]>(`/admin/employees?limit=100&offset=${staff.length}`)
      setStaff(current => [...current, ...rows]); setStaffHasMore(rows.length === 100)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }

  async function changeRole(person: Staff, role: string) {
    if (role === person.local_role) return
    const reason = window.prompt(`Причина изменения роли сотрудника ${person.name}`)?.trim()
    if (!reason) return
    if (reason.length < 10) { setError('Укажите причину не короче 10 символов.'); return }
    if (!window.confirm(`Назначить роль «${roleNames[role]}» сотруднику ${person.name}?`)) return
    setSaving(true); setError('')
    try {
      const updated = await request<Staff>(`/admin/employees/${person.id}/role`, { method: 'PUT', body: JSON.stringify({ role, reason }) })
      setStaff(rows => rows.map(row => row.id === updated.id ? updated : row))
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }

  async function open(id: string) {
    setError('')
    setCopyIntoSection(null)
    setMaterialTarget(null)
    setSelectedMaterialCampaign(null)
    try {
      const [courseData, campaignsData] = await Promise.all([
        request<Course>(`/admin/courses/${id}`),
        request<Campaign[]>(`/admin/campaigns?target_type=course&target_id=${id}`),
      ])
      setCourse(courseData); setCourseCampaigns(campaignsData)
    } catch (e) { setError((e as Error).message) }
  }
  async function openMaterial(type: 'course_article' | 'course_test', id: string, title: string) {
    setError('')
    try {
      const rows = await request<Campaign[]>(`/admin/campaigns?target_type=${type}&target_id=${id}`)
      setMaterialCampaigns(rows)
      setSelectedMaterialCampaign(null)
      setMaterialTarget({ type, id, title })
    } catch (e) { setError((e as Error).message) }
  }
  async function create() {
    const title = window.prompt('Название курса')?.trim()
    if (!title) return
    setSaving(true); setError('')
    try {
      const created = await request<Course>('/admin/courses', { method: 'POST', body: JSON.stringify({ title }) })
      setCourses(old => [created, ...old]); await open(created.id)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function copyCourse() {
    if (!course || !window.confirm(`Создать независимую копию курса «${course.title}»?`)) return
    setSaving(true); setError('')
    try {
      const copied = await request<Course>(`/admin/courses/${course.id}/copy`, { method: 'POST' })
      setCourses(rows => [copied, ...rows]); setCourse(copied)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function save() {
    if (!course) return
    setSaving(true); setError('')
    try {
      const updated = await request<Course>(`/admin/courses/${course.id}`, { method: 'PUT', body: JSON.stringify({ title: course.title, description: course.description, mode: course.mode, row_version: course.row_version }) })
      setCourse({ ...course, ...updated }); setCourses(old => old.map(item => item.id === updated.id ? updated : item))
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function addSection() {
    if (!course) return
    const title = window.prompt('Название раздела')?.trim()
    if (!title) return
    setSaving(true); setError('')
    try {
      const section = await request<Section & { row_version: number }>(`/admin/courses/${course.id}/sections`, { method: 'POST', body: JSON.stringify({ title, row_version: course.row_version }) })
      setCourse({ ...course, row_version: section.row_version, sections: [...(course.sections ?? []), section] })
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function renameSection(section: Section) {
    if (!course) return
    const title = window.prompt('Название раздела', section.title)?.trim()
    if (!title || title === section.title) return
    setSaving(true); setError('')
    try {
      const changed = await request<Section & { row_version: number }>(`/admin/courses/${course.id}/sections/${section.id}`, { method: 'PUT', body: JSON.stringify({ title, row_version: course.row_version }) })
      setCourse({ ...course, row_version: changed.row_version, sections: course.sections?.map(row => row.id === section.id ? { ...row, title: changed.title } : row) })
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function addArticle(section: Section) {
    if (!course) return
    const title = window.prompt('Название статьи курса')?.trim()
    if (!title) return
    setSaving(true); setError('')
    try {
      const created = await request<CourseItem & { row_version: number }>(`/admin/courses/${course.id}/sections/${section.id}/articles`, { method: 'POST', body: JSON.stringify({ title, row_version: course.row_version }) })
      setCourse({ ...course, row_version: created.row_version, sections: course.sections?.map(row => row.id === section.id ? { ...row, items: [...(row.items ?? []), created] } : row) })
      setCourseArticleId(created.article_id)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function copyItem(section: Section, item: CourseItem) {
    if (!course || !window.confirm(`Создать независимую копию материала «${item.title}» в разделе «${section.title}»?`)) return
    setSaving(true); setError('')
    try {
      await request(`/admin/courses/${course.id}/sections/${section.id}/copy-item`, { method: 'POST',
        body: JSON.stringify({ source_item_id: item.id, row_version: course.row_version }) })
      await open(course.id)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function addTest(section: Section) {
    if (!course) return
    const title = window.prompt('Название теста')?.trim()
    if (!title) return
    setSaving(true); setError('')
    try {
      const created = await request<CourseItem & { row_version: number }>(`/admin/courses/${course.id}/sections/${section.id}/tests`, { method: 'POST', body: JSON.stringify({ title, row_version: course.row_version }) })
      setCourse({ ...course, row_version: created.row_version, sections: course.sections?.map(row => row.id === section.id ? { ...row, items: [...(row.items ?? []), created] } : row) })
      setCourseTestId(created.test_id)
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }
  async function returnFromArticle() {
    setCourseArticleId(null)
    if (course) await open(course.id)
  }
  async function returnFromTest() {
    setCourseTestId(null)
    if (course) await open(course.id)
  }
  async function activateCourse() {
    if (!course || !window.confirm('Сделать курс доступным для назначения? Сотрудники пока не будут назначены.')) return
    setSaving(true); setError('')
    try {
      const activated = await request<{ status: string; row_version: number }>(`/admin/courses/${course.id}/activate`, { method: 'POST', body: JSON.stringify({ row_version: course.row_version, confirmed: true }) })
      setCourse({ ...course, status: activated.status, row_version: activated.row_version })
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }

  async function reorderProgram(sections: Section[]) {
    if (!course) return
    setSaving(true); setError('')
    try {
      const result = await request<{ row_version: number }>(`/admin/courses/${course.id}/program/order`, {
        method: 'PUT', body: JSON.stringify({ row_version: course.row_version,
          sections: sections.map(section => ({ id: section.id, item_ids: (section.items || []).map(item => item.id) })) }),
      })
      setCourse({ ...course, row_version: result.row_version, sections })
    } catch (e) { setError((e as Error).message) } finally { setSaving(false) }
  }

  function moveSection(index: number, direction: -1 | 1) {
    if (!course?.sections || saving) return
    const next = [...course.sections]
    const other = index + direction
    if (other < 0 || other >= next.length) return
    ;[next[index], next[other]] = [next[other], next[index]]
    void reorderProgram(next)
  }

  function dropProgram(event: DragEvent, targetSectionId: string, targetItemId?: string) {
    event.preventDefault(); event.stopPropagation()
    if (!course?.sections || !canEdit || saving) return
    let dragged: { type: 'section' | 'item'; id: string }
    try { dragged = JSON.parse(event.dataTransfer.getData('application/rtm-program')) }
    catch { return }
    const sections = course.sections.map(section => ({ ...section, items: [...(section.items || [])] }))
    if (dragged.type === 'section') {
      const from = sections.findIndex(section => section.id === dragged.id)
      const to = sections.findIndex(section => section.id === targetSectionId)
      if (from < 0 || to < 0 || from === to) return
      const [moved] = sections.splice(from, 1)
      sections.splice(to, 0, moved)
    } else if (dragged.type === 'item') {
      const source = sections.find(section => section.items?.some(item => item.id === dragged.id))
      const target = sections.find(section => section.id === targetSectionId)
      if (!source || !target) return
      const index = source.items!.findIndex(item => item.id === dragged.id)
      const [moved] = source.items!.splice(index, 1)
      const insertAt = targetItemId ? target.items!.findIndex(item => item.id === targetItemId) : target.items!.length
      target.items!.splice(insertAt < 0 ? target.items!.length : insertAt, 0, moved)
    }
    void reorderProgram(sections)
  }

  const canEdit = !!user && rank[user.role] >= rank.editor
  return <>
    <header><b className="brand">RTM<span>Education</span></b>{user && (view === 'admin' ? <nav aria-label="Разделы админки"><button className={adminTab === 'courses' ? 'active' : ''} onClick={() => { setAdminTab('courses'); setCourse(null); setCourseArticleId(null); setCourseTestId(null); setCampaignOpen(false) }}>Курсы</button><button className={adminTab === 'revisions' ? 'active' : ''} onClick={() => { setAdminTab('revisions'); setCourse(null) }}>Управление редакциями</button><button className={adminTab === 'reviews' ? 'active' : ''} onClick={() => { setAdminTab('reviews'); setCourse(null) }}>Центр проверок</button><button className={adminTab === 'knowledge' ? 'active' : ''} disabled={rank[user.role] < rank.editor} onClick={() => { setAdminTab('knowledge'); setCourse(null) }}>База знаний</button><button className={adminTab === 'employees' ? 'active' : ''} disabled={rank[user.role] < rank.admin} onClick={() => { setAdminTab('employees'); setCourse(null) }}>Сотрудники</button><button className={adminTab === 'settings' ? 'active' : ''} disabled={rank[user.role] < rank.admin} onClick={() => { setAdminTab('settings'); setCourse(null); setMaterialTarget(null) }}>Настройки</button></nav> : <nav aria-label="Разделы"><button className={userTab === 'learning' ? 'active' : ''} onClick={() => setUserTab('learning')}>Обучение</button><button className={userTab === 'knowledge' ? 'active' : ''} onClick={() => setUserTab('knowledge')}>База знаний</button><button className={userTab === 'profile' ? 'active' : ''} onClick={() => setUserTab('profile')}>Профиль</button></nav>)}<small>{user?.name ?? 'RTM Обучение Next'}</small>{user && rank[user.role] >= rank.teacher && <button className="switch-view" onClick={() => { setView(view === 'admin' ? 'user' : 'admin'); setCourse(null); setCourseArticleId(null); setCourseTestId(null); setCampaignOpen(false); setAdminTab('courses') }}>{view === 'admin' ? 'К обучению' : 'Админка'}</button>}</header>
    <main>
      <Suspense fallback={<p role="status">Загружаем раздел…</p>}>
      {loading && <p role="status">Загружаем профиль…</p>}
      {error && <div className="error" role="alert">{error}</div>}
      {!loading && user && view === 'user' && (userTab === 'learning' ? <LearningPanel tab={learningTab} onTabChange={setLearningTab} /> : userTab === 'knowledge' ? <KnowledgePanel mode="user" role={user.role} /> : <ProfilePanel />)}
      {!loading && user && view === 'admin' && adminTab === 'settings' && rank[user.role] >= rank.admin && <SettingsPanel />}
      {!loading && user && view === 'admin' && adminTab === 'knowledge' && rank[user.role] >= rank.editor && <KnowledgePanel mode="admin" role={user.role} />}
      {!loading && user && view === 'admin' && adminTab === 'revisions' && rank[user.role] >= rank.editor && <RevisionPanel />}
      {!loading && user && view === 'admin' && adminTab === 'revisions' && rank[user.role] === rank.teacher && <RevisionAssignments />}
      {!loading && user && view === 'admin' && adminTab === 'reviews' && rank[user.role] >= rank.teacher && <ReviewPanel />}
      {!loading && user && view === 'admin' && adminTab === 'employees' && rank[user.role] >= rank.admin && <>
        <div className="crumb">Рабочее пространство / Сотрудники</div>
        <div className="heading"><div><h1>Сотрудники</h1><p>Роли определяют доступ к управлению обучением.</p></div></div>
        <div className="search"><input aria-label="Поиск сотрудников" placeholder="Имя или ID Битрикс24" value={staffSearch} onChange={e => setStaffSearch(e.target.value)} /><span>Сотрудников: {staff.length}</span></div>
        <div className="table"><table><thead><tr><th>Сотрудник</th><th>ID Битрикс24</th><th>Роль</th><th>Статус</th></tr></thead><tbody>{staff.filter(person => `${person.name} ${person.bitrix_id}`.toLocaleLowerCase('ru-RU').includes(staffSearch.toLocaleLowerCase('ru-RU'))).map(person => <tr key={person.id}><td><b>{person.name}</b></td><td>{person.bitrix_id}</td><td>{person.bitrix_id === 36 ? <span>Разработчик · защищено</span> : person.id === user.id ? <span>{roleNames[person.effective_role]} · ваша роль</span> : <select aria-label={`Роль: ${person.name}`} value={person.local_role} disabled={!person.active || saving} onChange={e => changeRole(person, e.target.value)}><option value="employee">Пользователь</option><option value="teacher">Преподаватель</option><option value="editor">Редактор</option><option value="admin">Администратор</option></select>}{person.bitrix_id !== 36 && person.effective_role !== person.local_role && <small className="role-note">Права администратора получены из Битрикс24</small>}</td><td>{person.active ? 'Активен' : 'Неактивен'}</td></tr>)}</tbody></table>{staff.length === 0 && <div className="empty">Сотрудники появятся после входа через Битрикс24.</div>}</div>{staffHasMore && <button className="load-more" disabled={saving} onClick={loadMoreStaff}>Показать ещё</button>}
      </>}
      {!loading && user && view === 'admin' && adminTab === 'courses' && rank[user.role] >= rank.teacher && course && courseArticleId && <CourseArticleEditor courseId={course.id} articleId={courseArticleId} canEdit={canEdit} onBack={returnFromArticle} />}
      {!loading && user && view === 'admin' && adminTab === 'courses' && rank[user.role] >= rank.teacher && course && courseTestId && <TestEditor testId={courseTestId} onBack={returnFromTest} />}
      {!loading && user && view === 'admin' && adminTab === 'courses' && rank[user.role] >= rank.teacher && course && campaignOpen && !courseArticleId && !courseTestId && <CampaignWizard key={selectedCampaign?.id ?? 'new'} targetId={course.id} targetTitle={course.title} initialCampaign={selectedCampaign} onBack={() => { setCampaignOpen(false); setSelectedCampaign(null); void open(course.id) }} />}
      {!loading && user && view === 'admin' && adminTab === 'courses' && rank[user.role] >= rank.teacher && course && materialTarget && <><CampaignWizard key={selectedMaterialCampaign?.id ?? materialTarget.id} targetType={materialTarget.type} targetId={materialTarget.id} targetTitle={materialTarget.title} initialCampaign={selectedMaterialCampaign} onBack={() => { setMaterialTarget(null); setSelectedMaterialCampaign(null); void open(course.id) }} />{materialCampaigns.length > 0 && <section className="panel"><h2>Кампании материала</h2>{materialCampaigns.map(item => <button key={item.id} onClick={() => setSelectedMaterialCampaign(item)}>{item.title} · {item.status === 'active' ? 'активна' : 'черновик'} · получателей: {item.recipient_count}</button>)}</section>}</>}
      {!loading && user && view === 'admin' && adminTab === 'courses' && rank[user.role] >= rank.teacher && !courseArticleId && !courseTestId && !campaignOpen && !materialTarget && (!course ? <>
        <div className="crumb">Рабочее пространство / Курсы</div>
        <div className="heading"><div><h1>Курсы</h1><p>Черновики и действующие программы обучения.</p></div>{canEdit && <button className="primary" disabled={saving} onClick={create}>Создать курс</button>}</div>
        <div className="search"><input aria-label="Поиск по названию курса" placeholder="Поиск по названию курса" value={search} onChange={e => setSearch(e.target.value)} /><span>Курсов: {courses.length}</span></div>
        <div className="table"><table><thead><tr><th>Курс</th><th>Статус</th><th>Режим</th><th>Изменён</th></tr></thead><tbody>{courses.map(item => <tr key={item.id} tabIndex={0} onClick={() => open(item.id)} onKeyDown={e => e.key === 'Enter' && open(item.id)}><td><b>{item.title}</b></td><td>{item.status === 'draft' ? 'Черновик' : item.status}</td><td>{item.mode === 'free' ? 'Свободный' : 'Последовательный'}</td><td>{new Date(item.updated_at).toLocaleDateString('ru-RU')}</td></tr>)}</tbody></table>{courses.length === 0 && <div className="empty">Курсов пока нет.</div>}</div>
      </> : <>
        <button className="back" onClick={() => { setCourse(null); setCourseArticleId(null); setCourseTestId(null); setCampaignOpen(false) }}>← К курсам</button>
        <div className="heading"><div><h1>{course.title}</h1><p>{course.status === 'active' ? 'Доступен для назначения' : 'Черновик'} · версия {course.row_version}</p></div><div className="course-actions">{canEdit && <button className="primary" onClick={save} disabled={saving}>{saving ? 'Сохраняем…' : 'Сохранить'}</button>}{canEdit && <button onClick={copyCourse} disabled={saving}>Создать копию</button>}{canEdit && course.status === 'draft' && <button onClick={activateCourse} disabled={saving}>Сделать доступным</button>}{course.status === 'active' && <button onClick={() => setCampaignOpen(true)}>Назначить обучение</button>}</div></div>
        <div className="panel"><label>Название курса<input value={course.title} disabled={!canEdit} onChange={e => setCourse({ ...course, title: e.target.value })} /></label><label>Описание курса<textarea value={course.description} disabled={!canEdit} onChange={e => setCourse({ ...course, description: e.target.value })} /></label><label>Режим прохождения<select value={course.mode} disabled={!canEdit} onChange={e => setCourse({ ...course, mode: e.target.value as Course['mode'] })}><option value="free">Свободный</option><option value="sequential">Последовательный</option></select></label></div>
        <div className="panel"><div className="panel-head"><h2>Программа</h2>{canEdit && <button disabled={saving} onClick={addSection}>Добавить раздел</button>}</div>{course.sections?.map((section, index) => <section key={section.id} className="course-section" onDragOver={e => e.preventDefault()} onDrop={e => dropProgram(e, section.id)}><div className="course-section-head"><h3 draggable={canEdit && !saving} onDragStart={e => e.dataTransfer.setData('application/rtm-program', JSON.stringify({ type: 'section', id: section.id }))} title={canEdit ? 'Перетащите для изменения порядка' : undefined}>{index + 1}. {section.title}</h3>{canEdit && <div><button aria-label={`Поднять раздел ${section.title}`} disabled={saving || index === 0} onClick={() => moveSection(index, -1)}>↑</button><button aria-label={`Опустить раздел ${section.title}`} disabled={saving || index === (course.sections?.length ?? 0) - 1} onClick={() => moveSection(index, 1)}>↓</button><button disabled={saving} onClick={() => renameSection(section)}>Переименовать</button><button disabled={saving} onClick={() => addArticle(section)}>Добавить статью</button><button disabled={saving} onClick={() => addTest(section)}>Добавить тест</button><button disabled={saving} onClick={() => setCopyIntoSection(section)}>Копировать из другого курса</button></div>}</div>{section.items?.map(item => <div className="course-item-row" key={item.id}><button className="course-item" draggable={canEdit && !saving} onDragStart={e => { e.stopPropagation(); e.dataTransfer.setData('application/rtm-program', JSON.stringify({ type: 'item', id: item.id })) }} onDragOver={e => e.preventDefault()} onDrop={e => dropProgram(e, section.id, item.id)} disabled={item.kind === 'article' ? !item.article_id : !item.test_id} onClick={() => item.kind === 'article' ? item.article_id && setCourseArticleId(item.article_id) : item.test_id && setCourseTestId(item.test_id)}><span>{item.kind === 'article' ? 'Статья' : 'Тест'}</span><b>{item.title}</b><small>{item.required ? 'Обязательно' : 'Необязательно'}</small></button><button className="copy-item" onClick={() => { const id = item.kind === 'article' ? item.article_id : item.test_id; if (id) void openMaterial(item.kind === 'article' ? 'course_article' : 'course_test', id, item.title) }}>Назначить отдельно</button>{canEdit && <button className="copy-item" disabled={saving} onClick={() => copyItem(section, item)}>Копировать</button>}</div>)}{!section.items?.length && <p>В разделе пока нет материалов.</p>}</section>)}{course.sections?.length === 0 && <p>Добавьте первый раздел курса.</p>}</div>
      </>)}
      {!loading && user && view === 'admin' && adminTab === 'courses' && course && !campaignOpen && !courseArticleId && !courseTestId && courseCampaigns.length > 0 && <div className="panel"><h2>Кампании курса</h2><div className="table"><table><thead><tr><th>Кампания</th><th>Статус</th><th>Получатели</th><th></th></tr></thead><tbody>{courseCampaigns.map(item => <tr key={item.id}><td>{item.title}</td><td>{item.status === 'active' ? 'Активна' : 'Черновик'}</td><td>{item.recipient_count}</td><td><button onClick={() => { setSelectedCampaign(item); setCampaignOpen(true) }}>Открыть</button></td></tr>)}</tbody></table></div></div>}
      {course && copyIntoSection && <CopyMaterialDialog targetCourseId={course.id} targetSectionId={copyIntoSection.id}
        targetSectionTitle={copyIntoSection.title} rowVersion={course.row_version}
        onClose={() => setCopyIntoSection(null)} onCopied={() => open(course.id)} />}
      </Suspense>
    </main>
  </>
}
