import { useEffect, useState } from 'react'

type Status = {
  bitrix: { client_id_configured: boolean; installed: boolean; client_secret_configured: boolean; notification_scope_verified: boolean }
  google: { credentials_present: boolean; server_access_verified: boolean }
  delivery: { pending: number; retry: number; failed: number; uncertain: number }
}

export default function SettingsPanel() {
  const [status, setStatus] = useState<Status | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  async function refresh() {
    setLoading(true); setError('')
    try {
      const response = await fetch('/education-next/api/admin/settings/status', { credentials: 'include' })
      if (!response.ok) throw new Error(`Не удалось проверить состояние интеграций (${response.status}).`)
      setStatus(await response.json() as Status)
    } catch (cause) { setError((cause as Error).message) } finally { setLoading(false) }
  }

  useEffect(() => {
    let active = true
    fetch('/education-next/api/admin/settings/status', { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error(`Не удалось проверить состояние интеграций (${response.status}).`)
        return response.json() as Promise<Status>
      })
      .then(data => { if (active) setStatus(data) })
      .catch(cause => { if (active) setError((cause as Error).message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  return <>
    <div className="crumb">Рабочее пространство / Настройки</div>
    <div className="heading"><div><h1>Настройки</h1><p>Состояние подключений и доставки назначений.</p></div><button onClick={() => void refresh()} disabled={loading}>Обновить состояние</button></div>
    {error && <div className="error" role="alert">{error}</div>}
    {loading && <p role="status">Проверяем состояние…</p>}
    {status && <div className="settings-grid">
      <section className="panel"><h2>Битрикс24</h2><p>Код приложения: {status.bitrix.client_id_configured ? 'задан' : 'не задан'}</p><p>Установка и токены: {status.bitrix.installed ? 'получены' : 'не подтверждены'}</p><p>Ключ приложения на сервере: {status.bitrix.client_secret_configured ? 'задан' : 'не задан'}</p><p>Право на персональные уведомления: {status.bitrix.notification_scope_verified ? 'проверено' : 'не проверено'}</p><small>Наличие токенов не подтверждает право на отправку уведомлений. Секреты здесь не показываются.</small></section>
      <section className="panel"><h2>Google Docs</h2><p>Файл серверного доступа: {status.google.credentials_present ? 'есть' : 'не настроен'}</p><p>Чтение приватных документов: {status.google.server_access_verified ? 'проверено' : 'не проверено на реальном документе'}</p><small>Публикация редакции со встроенным документом требует доступного серверного снимка.</small></section>
      <section className="panel"><h2>Доставка</h2><p>В очереди: {status.delivery.pending}</p><p>Ожидают повтора: {status.delivery.retry}</p><p>Ошибки: {status.delivery.failed}</p><p>Требуют сверки: {status.delivery.uncertain}</p><small>Статусы отдельных задач видны в их кампаниях.</small></section>
    </div>}
  </>
}
