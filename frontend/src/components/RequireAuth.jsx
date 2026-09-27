import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { api } from '../api'

// 路由保护：未登录跳登录页
export default function RequireAuth() {
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
        加载中…
      </div>
    )
  }
  return state.authed ? <Outlet /> : <Navigate to="/login" replace />
}
