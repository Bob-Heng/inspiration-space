import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { LangSelect, useLang } from '../i18n'

export default function LoginPage() {
  const navigate = useNavigate()
  const { t } = useLang()
  const [initialized, setInitialized] = useState(null) // null=加载中
  const [recoveryMethods, setRecoveryMethods] = useState([])
  const [view, setView] = useState('auth') // auth | recover
  const [method, setMethod] = useState(null) // null=选择找回方式 | 'phone' | 'birthday'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [phone, setPhone] = useState('')
  const [birthday, setBirthday] = useState('')
  const [recoverValue, setRecoverValue] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmNew, setConfirmNew] = useState('')
  const [notice, setNotice] = useState(null)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    api
      .authStatus()
      .then((d) => {
        setInitialized(d.initialized)
        setRecoveryMethods(d.recovery_methods ?? [])
      })
      .catch((err) => setError(err.message))
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setNotice(null)
    if (!initialized && password !== confirm) {
      setError(t('passwordMismatch'))
      return
    }
    setSubmitting(true)
    try {
      if (initialized) {
        await api.login(username, password)
      } else {
        await api.setup(username, password, phone.trim(), birthday)
      }
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function openRecover() {
    setView('recover')
    setMethod(null)
    setRecoverValue('')
    setNewPassword('')
    setConfirmNew('')
    setError(null)
    setNotice(null)
  }

  async function handleRecoverSubmit(e) {
    e.preventDefault()
    setError(null)
    if (newPassword !== confirmNew) {
      setError(t('passwordMismatch'))
      return
    }
    setSubmitting(true)
    try {
      await api.recover(method, recoverValue.trim(), newPassword)
      setView('auth')
      setMethod(null)
      setNotice(t('recoverSuccess'))
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (view === 'recover') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50">
        <div className="mb-4 flex w-full max-w-sm justify-end">
          <LangSelect />
        </div>
        <div className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
          <h1 className="text-center text-2xl font-bold text-slate-800">
            {t('recoverTitle')}
          </h1>
          {method === null ? (
            <div className="mt-6 space-y-2">
              {recoveryMethods.includes('phone') && (
                <button
                  type="button"
                  className="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                  onClick={() => {
                    setMethod('phone')
                    setError(null)
                  }}
                >
                  {t('recoverByPhone')}
                </button>
              )}
              {recoveryMethods.includes('birthday') && (
                <button
                  type="button"
                  className="w-full rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
                  onClick={() => {
                    setMethod('birthday')
                    setError(null)
                  }}
                >
                  {t('recoverByBirthday')}
                </button>
              )}
            </div>
          ) : (
            <form onSubmit={handleRecoverSubmit} className="mt-6">
              <label className="block text-sm text-slate-600">
                {method === 'phone' ? t('phoneInput') : t('birthdayInput')}
                <input
                  type={method === 'phone' ? 'text' : 'date'}
                  className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                  value={recoverValue}
                  onChange={(e) => setRecoverValue(e.target.value)}
                />
              </label>
              <label className="mt-4 block text-sm text-slate-600">
                {t('newPassword')}
                <input
                  type="password"
                  className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                />
              </label>
              <label className="mt-4 block text-sm text-slate-600">
                {t('confirmNewPassword')}
                <input
                  type="password"
                  className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                  value={confirmNew}
                  onChange={(e) => setConfirmNew(e.target.value)}
                  autoComplete="new-password"
                />
              </label>
              {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
              <button
                type="submit"
                disabled={submitting}
                className="mt-6 w-full rounded bg-slate-800 py-2 text-white hover:bg-slate-700 disabled:opacity-50"
              >
                {submitting ? t('submitting') : t('recoverSubmit')}
              </button>
            </form>
          )}
          <button
            type="button"
            className="mt-3 w-full text-center text-sm text-slate-500 hover:text-slate-800"
            onClick={() => {
              setView('auth')
              setMethod(null)
              setError(null)
            }}
          >
            {t('backToLogin')}
          </button>
        </div>
      </div>
    )
  }

  if (initialized === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500">
        {error ?? t('loading')}
      </div>
    )
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50">
      <div className="mb-4 flex w-full max-w-sm justify-end">
        <LangSelect />
      </div>
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-lg bg-white p-8 shadow"
      >
        <h1 className="text-center text-2xl font-bold text-slate-800">
          {t('appName')}
        </h1>
        <p className="mt-1 text-center text-sm text-slate-500">
          {initialized ? t('loginTitle') : t('setupTitle')}
        </p>

        <label className="mt-6 block text-sm text-slate-600">
          {t('username')}
          <input
            className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            placeholder={initialized ? '' : t('setupUsernamePlaceholder')}
          />
        </label>
        <label className="mt-4 block text-sm text-slate-600">
          {initialized ? t('password') : t('passwordSetup')}
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
              {t('confirmPassword')}
              <input
                type="password"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            <label className="mt-4 block text-sm text-slate-600">
              {t('phoneLabel')}
              <input
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </label>
            <label className="mt-4 block text-sm text-slate-600">
              {t('birthdayLabel')}
              <input
                type="date"
                className="mt-1 w-full rounded border border-slate-300 px-3 py-2 outline-none focus:border-slate-500"
                value={birthday}
                onChange={(e) => setBirthday(e.target.value)}
              />
            </label>
            <p className="mt-1 text-xs text-slate-400">{t('recoveryHint')}</p>
            <p className="mt-4 rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">
              {t('credentialWarning')}
            </p>
          </>
        )}

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        {notice && <p className="mt-3 text-sm text-green-600">{notice}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="mt-6 w-full rounded bg-slate-800 py-2 text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {submitting
            ? t('submitting')
            : initialized
              ? t('login')
              : t('setup')}
        </button>
        {initialized && recoveryMethods.length > 0 && (
          <button
            type="button"
            className="mt-3 w-full text-center text-sm text-slate-500 hover:text-slate-800"
            onClick={openRecover}
          >
            {t('forgotPassword')}
          </button>
        )}
      </form>
    </div>
  )
}
