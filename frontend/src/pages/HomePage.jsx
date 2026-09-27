import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import InspirationPanel from '../components/InspirationPanel'

export default function HomePage() {
  const navigate = useNavigate()

  async function handleLogout() {
    await api.logout().catch(() => {})
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center px-4 py-3">
          <h1 className="text-lg font-bold text-slate-800">灵感空间</h1>
          <div className="ml-auto flex items-center gap-4">
            <Link
              to="/viewpoints"
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              观点库
            </Link>
            <Link
              to="/review"
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              审议工作台
            </Link>
            <button
              className="text-sm text-slate-500 hover:text-slate-800"
              onClick={handleLogout}
            >
              登出
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-6">
        <InspirationPanel />
      </main>
    </div>
  )
}
