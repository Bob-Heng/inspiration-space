import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

export default function LoginPage() {
  const navigate = useNavigate()
  const [initialized, setInitialized] = useState(null) // null=加载中
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api
      .authStatus()
      .then((d) => setInitialized(d.initialized))
      .catch((err) => setError(err.message))
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    if (!initialized && password !== confirm) {
      setError('两次输入的密码不一致')
      return
    }
    setSubmitting(true)
    try {
      if (initialized) {
        await api.login(username, password)
      } else {
        await api.setup(username, password)
      }
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (initialized === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">
        {error ?? '加载中…'}
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg bg-white p-8 shadow"
      >
        <h1 className="text-center text-2xl font-bold text-slate-800">灵感空间</h1>
        <p className="mt-1 text-center text-sm text-slate-500">
          {initialized ? '请登录' : '首次使用，请设置你的账号'}
        </p>

        <label className="mt-6 block text-sm text-slate-600">
          用户名
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            placeholder={initialized ? '' : '给自己起个用户名'}
          />
        </label>
        <label className="mt-4 block text-sm text-slate-600">
          密码{initialized ? '' : '（至少 6 位）'}
          <input
            type="password"
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={initialized ? 'current-password' : 'new-password'}
          />
        </label>
        {!initialized && (
          <>
            <label className="mt-4 block text-sm text-slate-600">
              确认密码
              <input
                type="password"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            <p className="mt-4 rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">
              请妥善保管账号密码：本系统为单机应用，没有修改密码和找回密码功能，忘记密码将无法登录。
            </p>
          </>
        )}

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full rounded bg-slate-800 py-2 text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {submitting ? '提交中…' : initialized ? '登录' : '创建并进入'}
        </button>
      </form>
    </div>
  )
}
