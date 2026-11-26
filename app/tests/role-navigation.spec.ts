import { expect, test } from '@playwright/test'

const people = [
  { id: 'dev', bitrix_id: 36, name: 'Андрей Абрамов', local_role: 'employee', effective_role: 'developer', active: true },
  { id: 'student', bitrix_id: 73, name: 'Ученик', local_role: 'employee', effective_role: 'employee', active: true },
]

test('developer starts in learner view and can open role management', async ({ page }) => {
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const result = path.endsWith('/auth/me') ? { id: 'dev', name: 'Андрей Абрамов', role: 'developer' }
      : path.endsWith('/admin/employees') ? people : []
    if (path.endsWith('/admin/settings/status')) return route.fulfill({ json: {
      bitrix: { client_id_configured: true, installed: true, client_secret_configured: false, notification_scope_verified: false },
      google: { credentials_present: false, server_access_verified: false }, delivery: { pending: 2, retry: 0, failed: 0, uncertain: 0 },
    } })
    await route.fulfill({ json: result })
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Обучение' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Админка' })).toBeVisible()
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('navigation', { name: 'Разделы админки' }).getByRole('button', { name: 'Сотрудники' }).click()
  await expect(page.getByText('Разработчик · защищено')).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'Роль: Ученик' })).toBeVisible()
  await page.getByRole('navigation', { name: 'Разделы админки' }).getByRole('button', { name: 'Настройки' }).click()
  await expect(page.getByRole('heading', { name: 'Настройки' })).toBeVisible()
  await expect(page.getByText('Ключ приложения на сервере: не задан')).toBeVisible()
  await page.getByRole('button', { name: 'К обучению' }).click()
  await expect(page.getByRole('heading', { name: 'Обучение' })).toBeVisible()
})

test('ordinary employee has no admin entry', async ({ page }) => {
  await page.route('**/education-next/api/auth/me', route => route.fulfill({ json: { id: 'student', name: 'Ученик', role: 'employee' } }))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Обучение' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Админка' })).toHaveCount(0)
})

test('editor saves a knowledge article with structured text', async ({ page }) => {
  page.on('pageerror', error => console.error('Browser error:', error.message))
  let savedBody: unknown
  const article = { id: 'article-1', folder_id: 'folder-1', title: 'Инструкция', summary: '',
    body: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Начало' }] }] },
    row_version: 1, updated_at: '2026-11-25T12:00:00Z' }
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'editor', name: 'Редактор', role: 'editor' } })
    if (path.endsWith('/admin/knowledge') && route.request().method() === 'GET') return route.fulfill({ json: {
      folders: [{ id: 'folder-1', parent_id: null, title: 'Регламенты', description: '' }], articles: [article],
    } })
    if (path.endsWith('/admin/knowledge/articles/article-1') && route.request().method() === 'PUT') {
      savedBody = route.request().postDataJSON().body
      return route.fulfill({ json: { ...article, body: savedBody, row_version: 2 } })
    }
    return route.fulfill({ json: [] })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('navigation', { name: 'Разделы админки' }).getByRole('button', { name: 'База знаний' }).click()
  await page.getByRole('row', { name: /Инструкция/ }).click()
  await page.locator('.article-editor [contenteditable="true"]').fill('Обновлённый текст')
  await page.getByRole('button', { name: 'Сохранить статью' }).click()
  await expect.poll(() => JSON.stringify(savedBody)).toContain('Обновлённый текст')
})

test('article autosave shows a failed save and allows retry', async ({ page }) => {
  let saves = 0
  const article = { id: 'article-1', folder_id: 'folder-1', title: 'Инструкция', summary: '',
    body: { type: 'doc', content: [{ type: 'paragraph' }] }, row_version: 1, updated_at: '2026-11-25T12:00:00Z' }
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'editor', name: 'Редактор', role: 'editor' } })
    if (path.endsWith('/admin/knowledge') && route.request().method() === 'GET') return route.fulfill({ json: {
      folders: [{ id: 'folder-1', parent_id: null, title: 'Регламенты', description: '' }], articles: [article],
    } })
    if (path.endsWith('/admin/knowledge/articles/article-1') && route.request().method() === 'PUT') {
      saves++
      return saves === 1 ? route.fulfill({ status: 503, json: { detail: 'Temporary failure' } })
        : route.fulfill({ json: { ...article, body: route.request().postDataJSON().body, row_version: 2 } })
    }
    return route.fulfill({ json: [] })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('navigation', { name: 'Разделы админки' }).getByRole('button', { name: 'База знаний' }).click()
  await page.getByRole('row', { name: /Инструкция/ }).click()
  await page.locator('.article-editor [contenteditable="true"]').fill('Текст для автосохранения')
  await expect(page.locator('.article-page [role="alert"]')).toContainText('Автосохранение не удалось')
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('button', { name: '← К статьям' }).click()
  await expect(page.locator('.article-editor [contenteditable="true"]')).toContainText('Текст для автосохранения')
  await page.getByRole('button', { name: 'Сохранить статью' }).click()
  await expect.poll(() => saves).toBe(2)
  await expect(page.locator('.article-page [role="status"]')).toHaveText('Сохранено')
})

test('knowledge article renders a live Google document inside the app', async ({ page }) => {
  const article = { id: 'article-google', folder_id: 'folder-1', title: 'Регламент', summary: '',
    body: { type: 'doc', content: [{ type: 'google_document', attrs: {
      fileId: 'doc123456', sourceUrl: 'https://docs.google.com/document/d/doc123456/edit',
    } }] }, row_version: 1, updated_at: '2026-11-25T12:00:00Z' }
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'editor', name: 'Редактор', role: 'editor' } })
    if (path.endsWith('/admin/knowledge')) return route.fulfill({ json: {
      folders: [{ id: 'folder-1', parent_id: null, title: 'Регламенты', description: '' }], articles: [article],
    } })
    if (path.endsWith('/google/articles/article-google/documents/doc123456')) return route.fulfill({ json: {
      title: 'Исходный регламент', revision_id: 'google-rev-1', fetched_at: '2026-11-26T00:00:00Z',
      blocks: [{ type: 'paragraph', style: 'HEADING_1', text: 'Правила работы' },
        { type: 'paragraph', style: 'NORMAL_TEXT', text: 'Текст из Google Docs' }],
    } })
    return route.fulfill({ json: [] })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('navigation', { name: 'Разделы админки' }).getByRole('button', { name: 'База знаний' }).click()
  await page.getByRole('row', { name: /Регламент/ }).click()
  await expect(page.locator('.google-embed')).toContainText('Текст из Google Docs')
  await expect(page.locator('.google-embed')).toContainText('Исходный регламент')
})

test('editor embeds a RUTUBE video inside a knowledge article', async ({ page }) => {
  const article = { id: 'article-1', folder_id: 'folder-1', title: 'Видеоинструкция', summary: '',
    body: { type: 'doc', content: [{ type: 'paragraph' }] }, row_version: 1, updated_at: '2026-11-25T12:00:00Z' }
  let saved: Record<string, unknown> | undefined
  await page.route('https://rutube.ru/**', route => route.fulfill({ body: '' }))
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'admin', name: 'Администратор', role: 'admin' } })
    if (path.endsWith('/admin/employees/departments')) return route.fulfill({ json: [] })
    if (path.endsWith('/admin/courses')) return route.fulfill({ json: [] })
    if (path.endsWith('/admin/knowledge') && route.request().method() === 'GET') return route.fulfill({ json: {
      folders: [{ id: 'folder-1', parent_id: null, title: 'Инструкции', description: '' }], articles: [article],
    } })
    if (path.endsWith('/admin/media/rutube')) return route.fulfill({ status: 201, json: { id: 'asset-1', kind: 'video', title: 'Видео RUTUBE', source_type: 'rutube' } })
    if (path.endsWith('/media/asset-1/info')) return route.fulfill({ json: { id: 'asset-1', kind: 'video', title: 'Видео RUTUBE', source_type: 'rutube', embed_url: 'https://rutube.ru/play/embed/abc123/', file_url: null } })
    if (path.endsWith('/admin/knowledge/articles/article-1') && route.request().method() === 'PUT') {
      saved = route.request().postDataJSON().body
      return route.fulfill({ json: { ...article, body: saved, row_version: 2 } })
    }
    return route.fulfill({ json: [] })
  })
  page.on('dialog', dialog => dialog.accept('https://rutube.ru/video/abc123/'))
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('navigation', { name: 'Разделы админки' }).getByRole('button', { name: 'База знаний' }).click()
  await page.getByRole('row', { name: /Видеоинструкция/ }).click()
  await page.getByRole('button', { name: 'RUTUBE' }).click()
  await expect(page.getByTitle('Видео RUTUBE')).toBeVisible()
  await page.getByRole('button', { name: 'Сохранить статью' }).click()
  await expect.poll(() => JSON.stringify(saved)).toContain('"type":"mediaEmbed"')
})

test('editor creates a course article and returns to its program', async ({ page }) => {
  const course = { id: 'course-1', title: 'Вводный курс', description: '', mode: 'free', status: 'draft', row_version: 2, updated_at: '2026-11-25T12:00:00Z', sections: [
    { id: 'section-1', title: 'Основы', position: 0, items: [] as Record<string, unknown>[] },
  ] }
  const article = { id: 'article-1', title: 'Правила', summary: '', body: { type: 'doc', content: [{ type: 'paragraph' }] }, row_version: 1 }
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'editor', name: 'Редактор', role: 'editor' } })
    if (path.endsWith('/admin/courses')) return route.fulfill({ json: [course] })
    if (path.endsWith('/admin/courses/course-1')) return route.fulfill({ json: course })
    if (path.endsWith('/sections/section-1/articles') && route.request().method() === 'POST') {
      course.row_version = 3
      course.sections[0].items.push({ id: 'item-1', kind: 'article', article_id: 'article-1', test_id: null, title: 'Правила', position: 0, required: true })
      return route.fulfill({ json: { ...course.sections[0].items[0], row_version: 3 }, status: 201 })
    }
    if (path.endsWith('/articles/article-1') && route.request().method() === 'GET') return route.fulfill({ json: article })
    return route.fulfill({ json: [] })
  })
  page.on('dialog', dialog => dialog.accept('Правила'))
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('row', { name: /Вводный курс/ }).click()
  await page.getByRole('button', { name: 'Добавить статью' }).click()
  await expect(page.getByRole('button', { name: 'К программе курса' })).toBeVisible()
  await page.getByRole('button', { name: 'К программе курса' }).click()
  await expect(page.getByRole('button', { name: /Статья Правила/ })).toBeVisible()
})

test('learner opens assigned course and confirms its article', async ({ page }) => {
  let status = 'not_started'
  let completed = false
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'learner', name: 'Ученик', role: 'employee' } })
    if (path.endsWith('/my/assignments')) return route.fulfill({ json: [{ id: 'assignment-1', title: 'Вводный курс', target_type: 'course', status, due_at: null, is_overdue: false }] })
    if (path.endsWith('/my/assignments/assignment-1') && route.request().method() === 'GET') return route.fulfill({ json: {
      id: 'assignment-1', title: 'Вводный курс', status, target_type: 'course', due_at: null,
      required_total: 1, required_done: completed ? 1 : 0,
      course: { title: 'Вводный курс', description: '', mode: 'free', sections: [{ id: 'section-1', title: 'Основы', items: [{
        id: 'item-1', kind: 'article', title: 'Правила', required: true, completed, locked: false,
        article: { id: 'article-1', summary: '', body: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Текст правил' }] }] } },
      }] }] },
    } })
    if (path.endsWith('/my/assignments/assignment-1/start')) { status = 'in_progress'; return route.fulfill({ json: { status } }) }
    if (path.endsWith('/my/assignments/assignment-1/items/item-1/acknowledge')) {
      completed = true; status = 'completed'; return route.fulfill({ json: { completed: true, assignment_status: status } })
    }
    return route.fulfill({ json: [] })
  })
  await page.goto('/')
  await page.getByRole('row', { name: /Вводный курс/ }).click()
  await page.getByRole('button', { name: 'Начать обучение' }).click()
  await page.getByRole('button', { name: /Статья Правила/ }).click()
  await expect(page.getByText('Текст правил')).toBeVisible()
  await page.getByRole('button', { name: 'Ознакомился' }).click()
  await expect(page.getByText('Обязательных материалов: 1 из 1')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Статья Правила Завершено' })).toBeVisible()
})

test('teacher prepares and confirms a course campaign', async ({ page }) => {
  const course = { id: 'course-1', title: 'Вводный курс', description: '', mode: 'free', status: 'active', row_version: 3,
    updated_at: '2026-11-25T12:00:00Z', sections: [] }
  let draftPayload: Record<string, unknown> | undefined
  let launched = false
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'teacher', name: 'Преподаватель', role: 'teacher' } })
    if (path.endsWith('/admin/courses')) return route.fulfill({ json: [course] })
    if (path.endsWith('/admin/courses/course-1')) return route.fulfill({ json: course })
    if (path.endsWith('/admin/employees/recipients')) return route.fulfill({ json: [{ bitrix_id: 73, name: 'Ученик', can_review: false }] })
    if (path.endsWith('/admin/campaigns') && route.request().method() === 'GET') return route.fulfill({ json: launched ? [{ id: 'campaign-1', title: 'Вводный курс', status: 'active', recipient_count: 1 }] : [] })
    if (path.endsWith('/admin/campaigns') && route.request().method() === 'POST') {
      draftPayload = route.request().postDataJSON()
      return route.fulfill({ status: 201, json: { id: 'campaign-1', title: 'Вводный курс', status: 'draft', recipient_count: 1 } })
    }
    if (path.endsWith('/admin/campaigns/campaign-1/preview')) return route.fulfill({ json: {
      recipient_count: 1, example_recipient: 'Ученик', due_at: '2026-12-02T12:00:00Z',
      relative_due_is_estimate: true, task_title: 'Пройти курс «Вводный курс» — Ученик',
      task_description: 'Откройте приложение и пройдите курс до 02.12.2026.',
    } })
    if (path.endsWith('/admin/campaigns/campaign-1/launch')) { launched = true; return route.fulfill({ json: { id: 'campaign-1', title: 'Вводный курс', status: 'active', recipient_count: 1 } }) }
    if (path.endsWith('/admin/campaigns/campaign-1/assignments')) return route.fulfill({ json: [{ id: 'assignment-1', employee_name: 'Ученик', employee_bitrix_id: 73, status: 'not_started', due_at: null, is_overdue: false }] })
    if (path.endsWith('/admin/campaigns/campaign-1/delivery')) return route.fulfill({ json: { jobs: [], counts: { pending: 0, sent: 0, failed: 0 } } })
    return route.fulfill({ json: [] })
  })
  page.on('dialog', dialog => dialog.accept())
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('row', { name: /Вводный курс/ }).click()
  await page.getByRole('button', { name: 'Назначить обучение' }).click()
  await page.getByRole('checkbox', { name: /Ученик/ }).check()
  await page.getByRole('checkbox', { name: 'Создать задачу Bitrix24' }).check()
  await page.getByRole('button', { name: 'Сохранить черновик кампании' }).click()
  await expect.poll(() => draftPayload?.recipient_bitrix_ids).toEqual([73])
  await expect(page.getByRole('heading', { name: 'Предпросмотр задачи для Ученик' })).toBeVisible()
  await expect(page.getByText('Пройти курс «Вводный курс» — Ученик')).toBeVisible()
  await page.getByRole('button', { name: 'Подтвердить запуск' }).click()
  await expect(page.getByRole('heading', { name: 'Кампания запущена' })).toBeVisible()
  await page.getByRole('button', { name: 'Вернуться к курсу' }).click()
  await page.getByRole('row', { name: /Вводный курс Активна 1 Открыть/ }).getByRole('button', { name: 'Открыть' }).click()
  await page.getByRole('button', { name: 'Показать назначения' }).click()
  await expect(page.getByRole('cell', { name: 'Ученик' })).toBeVisible()
})

test('editor creates a test and saves a question', async ({ page }) => {
  const course = { id: 'course-1', title: 'Курс', description: '', mode: 'free', status: 'draft', row_version: 2,
    updated_at: '2026-11-25T12:00:00Z', sections: [{ id: 'section-1', title: 'Основы', position: 0, items: [] as Record<string, unknown>[] }] }
  const test = { id: 'test-1', title: 'Проверка', summary: '', time_limit_minutes: null, max_attempts: 1, min_correct: 0,
    shuffle_questions: false, shuffle_options: false, show_results: true, row_version: 1, questions: [] }
  let saved: Record<string, unknown> | undefined
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'editor', name: 'Редактор', role: 'editor' } })
    if (path.endsWith('/admin/courses')) return route.fulfill({ json: [course] })
    if (path.endsWith('/admin/courses/course-1')) return route.fulfill({ json: course })
    if (path.endsWith('/sections/section-1/tests') && route.request().method() === 'POST') {
      course.sections[0].items.push({ id: 'item-1', kind: 'test', article_id: null, test_id: 'test-1', title: 'Проверка', position: 0, required: true })
      return route.fulfill({ status: 201, json: { ...course.sections[0].items[0], row_version: 3 } })
    }
    if (path.endsWith('/admin/tests/test-1') && route.request().method() === 'GET') return route.fulfill({ json: test })
    if (path.endsWith('/admin/tests/test-1') && route.request().method() === 'PUT') {
      saved = route.request().postDataJSON()
      return route.fulfill({ json: { ...saved, row_version: 2 } })
    }
    return route.fulfill({ json: [] })
  })
  page.on('dialog', dialog => dialog.accept('Проверка'))
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Курс', exact: true }) }).click()
  await page.getByRole('button', { name: 'Добавить тест' }).click()
  await page.getByRole('button', { name: 'Добавить вопрос' }).click()
  await page.getByRole('textbox', { name: 'Формулировка' }).fill('Какой ответ верный?')
  await page.getByRole('textbox', { name: 'Вариант 1' }).fill('Да')
  await page.getByRole('textbox', { name: 'Вариант 2' }).fill('Нет')
  await page.getByRole('button', { name: 'Копировать вопрос' }).click()
  await page.locator('.test-question').nth(1).getByRole('textbox', { name: 'Формулировка' }).fill('Копия вопроса')
  await page.getByRole('button', { name: 'Поднять вопрос 2' }).click()
  await page.getByRole('button', { name: 'Сохранить тест' }).click()
  await expect.poll(() => (saved?.questions as { prompt: string }[] | undefined)?.[0]?.prompt).toBe('Копия вопроса')
  await expect(page.getByText('Сохранено')).toBeVisible()
})

test('teacher reviews a free answer in the review center', async ({ page }) => {
  let version = 1
  let status = 'pending'
  let draft: Record<string, { decision: string; comment: string }> = {}
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'teacher', name: 'Преподаватель', role: 'teacher' } })
    if (path.endsWith('/admin/courses')) return route.fulfill({ json: [] })
    if (path.endsWith('/admin/reviews') && method === 'GET') return route.fulfill({ json: [{ id: 'review-1', status, learner_name: 'Иван Иванов', campaign_title: 'Вводный курс', test_title: 'Проверка', created_at: '2026-11-25T12:00:00Z' }] })
    if (path.endsWith('/admin/reviews/review-1/claim')) { status = 'claimed'; version++; return route.fulfill({ json: detail() }) }
    if (path.endsWith('/admin/reviews/review-1/draft')) { draft = route.request().postDataJSON().decisions; version++; return route.fulfill({ json: detail() }) }
    if (path.endsWith('/admin/reviews/review-1/complete')) { status = 'completed'; version++; return route.fulfill({ json: detail() }) }
    if (path.endsWith('/admin/reviews/review-1')) return route.fulfill({ json: detail() })
    return route.fulfill({ json: [] })
  })
  function detail() { return { id: 'review-1', status, row_version: version, learner_name: 'Иван Иванов', campaign_title: 'Вводный курс', test_title: 'Проверка', claimed_by: status === 'pending' ? null : 'teacher', draft,
    questions: [
      { id: 'auto-1', kind: 'single', prompt: 'Выберите порядок', image_asset_id: null,
        options: [{ id: 'option-1', text: 'По инструкции', image_asset_id: null }], correct_option_ids: ['option-1'],
        submissions: [{ id: 'submission-0', version: 1, value: { option_ids: ['option-1'] }, is_correct: true, reviews: [] }] },
      { id: 'free-1', kind: 'free_text', prompt: 'Как действовать?', image_asset_id: null, options: [], correct_option_ids: [],
        submissions: [{ id: 'submission-1', version: 1, value: { text: 'По инструкции' }, is_correct: null, reviews: [] }] },
    ] } }
  page.on('dialog', dialog => dialog.accept())
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('navigation', { name: 'Разделы админки' }).getByRole('button', { name: 'Центр проверок' }).click()
  await page.getByRole('row', { name: /Иван Иванов/ }).click()
  await page.getByRole('button', { name: 'Взять в работу' }).click()
  await expect(page.getByText('Выбран · Верный ответ · По инструкции')).toBeVisible()
  await page.getByRole('button', { name: 'Принять' }).click()
  await page.getByRole('button', { name: 'Сохранить решения' }).click()
  await page.getByRole('button', { name: 'Завершить проверку' }).click()
  await expect(page.getByText('Проверка завершена.')).toBeVisible()
})

test('editor reorders course sections with accessible controls', async ({ page }) => {
  const course = { id: 'course-1', title: 'Курс', description: '', mode: 'free', status: 'draft', row_version: 2,
    updated_at: '2026-11-25T12:00:00Z', sections: [
      { id: 'first', title: 'Первый', position: 0, items: [] },
      { id: 'second', title: 'Второй', position: 1, items: [] },
    ] }
  let ordered: Record<string, unknown> | undefined
  await page.route('**/education-next/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/auth/me')) return route.fulfill({ json: { id: 'editor', name: 'Редактор', role: 'editor' } })
    if (path.endsWith('/admin/courses')) return route.fulfill({ json: [course] })
    if (path.endsWith('/admin/courses/course-1/program/order')) {
      ordered = route.request().postDataJSON()
      return route.fulfill({ json: { row_version: 3 } })
    }
    if (path.endsWith('/admin/courses/course-1')) return route.fulfill({ json: course })
    return route.fulfill({ json: [] })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Админка' }).click()
  await page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'Курс', exact: true }) }).click()
  await page.getByRole('button', { name: 'Поднять раздел Второй' }).click()
  await expect.poll(() => (ordered?.sections as { id: string }[] | undefined)?.[0]?.id).toBe('second')
  await expect(page.getByRole('heading', { name: '1. Второй' })).toBeVisible()
})
