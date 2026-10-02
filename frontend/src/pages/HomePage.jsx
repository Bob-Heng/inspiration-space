import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import InspirationPanel from '../components/InspirationPanel'
import PageHeader from '../components/PageHeader'
import ScrollElevator from '../components/ScrollElevator'
import { LangSelect, useLang } from '../i18n'

export default function HomePage() {
  const navigate = useNavigate()
  const { t } = useLang()

  async function handleLogout() {
    await api.logout().catch(() => {})
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <PageHeader
        current="home"
        subtitle={t('home')}
        extras={
          <>
            <LangSelect />
            <button
              className="text-sm text-slate-500 hover:text-slate-800"
              onClick={handleLogout}
            >
              {t('logout')}
            </button>
          </>
        }
      />
      <main className="mx-auto w-full max-w-7xl px-4 py-6">
        {/* 与审议工作台中栏（lg:col-span-6）等宽 */}
        <div className="lg:mx-auto lg:w-1/2">
          <InspirationPanel />
        </div>
      </main>
      <ScrollElevator />
    </div>
  )
}
