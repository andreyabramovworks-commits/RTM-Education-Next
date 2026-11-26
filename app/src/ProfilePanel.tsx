import { useEffect, useState } from 'react'

type Reward = { id: string; test_title: string; points: number; awarded_at: string }
type Profile = { name: string; points: number; rewards: Reward[] }

export default function ProfilePanel() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    fetch('/education-next/api/my/profile', { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 401
          ? 'Сессия закончилась. Откройте приложение из Битрикс24 заново.'
          : `Не удалось загрузить профиль (${response.status}).`)
        return response.json() as Promise<Profile>
      })
      .then(data => { if (active) setProfile(data) })
      .catch(cause => { if (active) setError((cause as Error).message) })
    return () => { active = false }
  }, [])

  return <div className="profile-page">
    <h1>Профиль</h1>
    {error && <div role="alert" className="error">{error}</div>}
    {!profile && !error && <p>Загружаем профиль…</p>}
    {profile && <>
      <div className="panel"><p>{profile.name}</p><h2>Баллы за тесты: {profile.points}</h2><p>Баллы начисляются один раз за каждый сданный тест в конкретном назначении.</p></div>
      <div className="panel"><h2>Последние награды</h2>
        {profile.rewards.length ? <ul>{profile.rewards.map(reward => <li key={reward.id}>
          <strong>{reward.test_title}</strong> · {reward.points} баллов · {new Date(reward.awarded_at).toLocaleDateString('ru-RU')}
        </li>)}</ul> : <p>Пока нет сданных тестов с наградой.</p>}
      </div>
    </>}
  </div>
}
