import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { api } from '../api'
import { useLang } from '../i18n'

// 路由保护：未登录跳登录页
export default function RequireAuth() {
  const { t } = useLang()
  const [state, setState] = useState({ loading: true, authed: false })

  useEffect(() => {
    api
      .me()
      .then(() => setState({ loading: false, authed: true }))
      .catch(() => setState({ loading: false, authed: false }))
  }, [])

  if (state.loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">
        {t('loading')}
      </div>
    )
  }
  return state.authed ? <Outlet /> : <Navigate to="/login" replace />
}
