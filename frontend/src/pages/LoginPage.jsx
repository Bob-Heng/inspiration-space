import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { LangSelect, useLang } from '../i18n'
import CardWall from '../components/login/CardWall'
import TracedBorder from '../components/login/TracedBorder'
import ShatterCanvas from '../components/login/ShatterCanvas'
import WarpCanvas from '../components/login/WarpCanvas'
import '../components/login/entry.css'

const SLOW_WALL =
  typeof window !== 'undefined' &&
  new URLSearchParams(window.location.search).has('slowwall')
// 调试用：?fx=shatter / ?fx=warp 直接演示登录成功后的过场（验收动画用）
const DEMO_FX =
  typeof window !== 'undefined'
    ? new URLSearchParams(window.location.search).get('fx')
    : null

// 文字全部浮现 → 开始描绘边框 的间隔
const TEXT_TO_TRACE_MS = 1100
// 描绘完成（1.5s 光束 + 输入框错峰延迟 0.3s）→ 可交互
const TRACE_MS = 1900

/** 描边输入框：外层锚定光束边框，内层承载抖动/闪红（key 重挂载以重播抖动） */
function TracedInput({ tracing, delay, shakeKey, children }) {
  return (
    <div
      className="lm-trace-host relative rounded-input bg-white"
      data-shatter-box="12"
    >
      <div
        key={shakeKey}
        className={`rounded-input ${shakeKey ? 'lm-shake lm-input-error' : ''}`}
      >
        {children}
      </div>
      <TracedBorder active={tracing} radius={12} delay={delay} />
    </div>
  )
}

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

  // 登录序列阶段：wall(卡墙) → text(文字浮现) → trace(光束描绘边框) → idle(可交互)
  // 登录成功：shatter(碎成粒子) → warp(星空穿梭) → 跳首页
  const [phase, setPhase] = useState(DEMO_FX === 'warp' ? 'warp' : 'wall')
  const [wallGone, setWallGone] = useState(DEMO_FX === 'warp')
  const [shake, setShake] = useState(0)

  useEffect(() => {
    api
      .authStatus()
      .then((d) => {
        setInitialized(d.initialized)
        setRecoveryMethods(d.recovery_methods ?? [])
      })
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    if (phase === 'text') {
      const id = setTimeout(() => setPhase('trace'), TEXT_TO_TRACE_MS)
      return () => clearTimeout(id)
    }
    if (phase === 'trace') {
      const id = setTimeout(() => setPhase('idle'), TRACE_MS)
      return () => clearTimeout(id)
    }
    // 调试钩子：?fx=shatter 在可交互后自动演示粒子碎裂
    if (phase === 'idle' && DEMO_FX === 'shatter') {
      const id = setTimeout(() => setPhase('shatter'), 500)
      return () => clearTimeout(id)
    }
    return undefined
  }, [phase])

  const textOn = phase !== 'wall'
  const tracing = phase === 'trace' || phase === 'idle' || phase === 'shatter'
  const gone = phase === 'shatter' || phase === 'warp'

  // 视图切换（登录 ↔ 找回 ↔ 找回方式）后重播文字浮现与边框描绘
  const viewKey = `${view}:${method ?? ''}:${initialized}`

  function enterHome() {
    sessionStorage.setItem('inspiration_entry', 'warp')
    navigate('/', { replace: true })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setNotice(null)
    if (!initialized && password !== confirm) {
      setError(t('passwordMismatch'))
      setShake((k) => k + 1)
      return
    }
    setSubmitting(true)
    try {
      if (initialized) {
        await api.login(username, password)
      } else {
        await api.setup(username, password, phone.trim(), birthday)
      }
      setPhase('shatter')
    } catch (err) {
      setError(err.message)
      setShake((k) => k + 1)
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
      setShake((k) => k + 1)
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
      setShake((k) => k + 1)
    } finally {
      setSubmitting(false)
    }
  }

  /** 文字模糊浮现：错峰延迟；extra 为附加 class（必须与动画 class 合并而非覆盖） */
  const blur = (delay, extra = '') => ({
    className: `${textOn ? 'lm-blur lm-blur--on' : 'lm-blur'} ${extra}`.trim(),
    style: { '--d': `${delay}ms` },
  })
  /** 非文字元素（按钮、链接、语言切换）：随描绘阶段显现 */
  const materialize = (delay, extra = '') => ({
    className: `${tracing ? 'lm-blur lm-blur--on' : 'lm-blur'} ${extra}`.trim(),
    style: { '--d': `${delay}ms` },
  })

  const inputCls =
    'w-full rounded-input bg-transparent px-3 py-2 text-sm text-ink outline-none'
  const labelCls = 'block text-sm text-ink-2'
  const primaryBtnCls =
    'mt-6 w-full rounded-pill bg-accent py-2.5 text-sm font-medium text-accent-ink shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift active:translate-y-0 disabled:opacity-50'
  // 金色 = 创造（首次创建账号）
  const goldBtnCls =
    'mt-6 w-full rounded-pill bg-accent-2 py-2.5 text-sm font-medium text-ink shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift active:translate-y-0 disabled:opacity-50'
  const linkBtnCls =
    'mt-3 w-full text-center text-sm text-ink-3 transition-colors duration-200 hover:text-ink'

  const appNameChars = Array.from(t('appName'))

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-paper">
      {!wallGone && (
        <CardWall
          timeScale={SLOW_WALL ? 5 : 1}
          onLastCardCenter={() =>
            setPhase((p) => (p === 'wall' ? 'text' : p))
          }
          onDone={() => setWallGone(true)}
        />
      )}

      <div
        className={`relative z-10 flex w-full max-w-sm flex-col px-4 ${gone ? 'lm-gone' : ''}`}
      >
        <div {...materialize(700, 'mb-4 flex justify-end')}>
          <span data-shatter>
            <LangSelect />
          </span>
        </div>

        {initialized === null ? (
          <p {...blur(0, 'text-center text-sm text-ink-2')}>
            {error ?? t('loading')}
          </p>
        ) : (
          <div key={viewKey} className="relative">
            {/* 卡片表面：随描绘阶段显现（文字先于表面浮现） */}
            <div
              aria-hidden="true"
              data-shatter-box="20"
              className={`lm-surface absolute inset-0 rounded-card bg-white shadow-card ${tracing ? 'lm-surface--on' : ''}`}
            />
            <TracedBorder active={tracing} radius={20} />
            <div className="relative p-8">
              {view === 'recover' ? (
                <>
                  <h1
                    {...blur(0, 'text-center font-display text-xl font-semibold text-ink')}
                    data-shatter
                  >
                    {t('recoverTitle')}
                  </h1>
                  {method === null ? (
                    <div className="mt-6 space-y-2.5">
                      {recoveryMethods.includes('phone') && (
                        <button
                          type="button"
                          {...materialize(200, 'w-full rounded-pill bg-paper-2 px-3 py-2.5 text-sm text-ink transition-colors duration-200 hover:bg-accent-soft')}
                          onClick={() => {
                            setMethod('phone')
                            setError(null)
                          }}
                          data-shatter
                        >
                          {t('recoverByPhone')}
                        </button>
                      )}
                      {recoveryMethods.includes('birthday') && (
                        <button
                          type="button"
                          {...materialize(300, 'w-full rounded-pill bg-paper-2 px-3 py-2.5 text-sm text-ink transition-colors duration-200 hover:bg-accent-soft')}
                          onClick={() => {
                            setMethod('birthday')
                            setError(null)
                          }}
                          data-shatter
                        >
                          {t('recoverByBirthday')}
                        </button>
                      )}
                    </div>
                  ) : (
                    <form onSubmit={handleRecoverSubmit} className="mt-6">
                      <div {...blur(200)} data-shatter>
                        <span {...blur(200, labelCls)}>
                          {method === 'phone'
                            ? t('phoneInput')
                            : t('birthdayInput')}
                        </span>
                        <TracedInput tracing={tracing} delay={0} shakeKey={shake}>
                          <input
                            type={method === 'phone' ? 'text' : 'date'}
                            className={`mt-1 ${inputCls}`}
                            value={recoverValue}
                            onChange={(e) => setRecoverValue(e.target.value)}
                          />
                        </TracedInput>
                      </div>
                      <div {...blur(290, 'mt-4')} data-shatter>
                        <span {...blur(290, labelCls)}>
                          {t('newPassword')}
                        </span>
                        <TracedInput tracing={tracing} delay={90} shakeKey={shake}>
                          <input
                            type="password"
                            className={`mt-1 ${inputCls}`}
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            autoComplete="new-password"
                          />
                        </TracedInput>
                      </div>
                      <div {...blur(380, 'mt-4')} data-shatter>
                        <span {...blur(380, labelCls)}>
                          {t('confirmNewPassword')}
                        </span>
                        <TracedInput tracing={tracing} delay={180} shakeKey={shake}>
                          <input
                            type="password"
                            className={`mt-1 ${inputCls}`}
                            value={confirmNew}
                            onChange={(e) => setConfirmNew(e.target.value)}
                            autoComplete="new-password"
                          />
                        </TracedInput>
                      </div>
                      {error && (
                        <p
                          key={`${error}-${shake}`}
                          className="lm-error-slide mt-3 text-sm text-danger"
                        >
                          {error}
                        </p>
                      )}
                      <div {...materialize(400)}>
                        <button
                          type="submit"
                          disabled={submitting}
                          className={primaryBtnCls}
                          data-shatter
                        >
                          {submitting ? t('submitting') : t('recoverSubmit')}
                        </button>
                      </div>
                    </form>
                  )}
                  <div {...materialize(500)}>
                    <button
                      type="button"
                      className={linkBtnCls}
                      onClick={() => {
                        setView('auth')
                        setMethod(null)
                        setError(null)
                      }}
                    >
                      {t('backToLogin')}
                    </button>
                  </div>
                </>
              ) : (
                <form onSubmit={handleSubmit}>
                  <h1
                    aria-label={t('appName')}
                    data-shatter
                    className="whitespace-nowrap text-center font-display text-2xl font-semibold tracking-tight text-ink"
                  >
                    {appNameChars.map((ch, i) =>
                      ch === ' ' ? (
                        <span key={i}> </span>
                      ) : (
                        <span
                          key={i}
                          aria-hidden="true"
                          {...blur(i * 90, 'inline-block')}
                        >
                          {ch}
                        </span>
                      ),
                    )}
                  </h1>
                  <p
                    {...blur(320, 'mt-1.5 text-center text-sm text-ink-2')}
                    data-shatter
                  >
                    {initialized ? t('loginTagline') : t('setupTitle')}
                  </p>

                  <div {...blur(430, 'mt-7')} data-shatter>
                    <span {...blur(430, labelCls)}>{t('username')}</span>
                    <TracedInput tracing={tracing} delay={0} shakeKey={shake}>
                      <input
                        className={`mt-1 ${inputCls}`}
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        autoComplete="username"
                        placeholder={
                          initialized ? '' : t('setupUsernamePlaceholder')
                        }
                      />
                    </TracedInput>
                  </div>
                  <div {...blur(520, 'mt-4')} data-shatter>
                    <span {...blur(520, labelCls)}>
                      {initialized ? t('password') : t('passwordSetup')}
                    </span>
                    <TracedInput tracing={tracing} delay={90} shakeKey={shake}>
                      <input
                        type="password"
                        className={`mt-1 ${inputCls}`}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete={
                          initialized ? 'current-password' : 'new-password'
                        }
                      />
                    </TracedInput>
                  </div>

                  {!initialized && (
                    <>
                      <div {...blur(600, 'mt-4')} data-shatter>
                        <span {...blur(600, labelCls)}>
                          {t('confirmPassword')}
                        </span>
                        <TracedInput tracing={tracing} delay={160} shakeKey={shake}>
                          <input
                            type="password"
                            className={`mt-1 ${inputCls}`}
                            value={confirm}
                            onChange={(e) => setConfirm(e.target.value)}
                            autoComplete="new-password"
                          />
                        </TracedInput>
                      </div>
                      <div {...blur(670, 'mt-4')} data-shatter>
                        <span {...blur(670, labelCls)}>{t('phoneLabel')}</span>
                        <TracedInput tracing={tracing} delay={230} shakeKey={0}>
                          <input
                            className={`mt-1 ${inputCls}`}
                            value={phone}
                            onChange={(e) => setPhone(e.target.value)}
                          />
                        </TracedInput>
                      </div>
                      <div {...blur(740, 'mt-4')} data-shatter>
                        <span {...blur(740, labelCls)}>
                          {t('birthdayLabel')}
                        </span>
                        <TracedInput tracing={tracing} delay={300} shakeKey={0}>
                          <input
                            type="date"
                            className={`mt-1 ${inputCls}`}
                            value={birthday}
                            onChange={(e) => setBirthday(e.target.value)}
                          />
                        </TracedInput>
                      </div>
                      <p
                        {...blur(800, 'mt-1.5 text-xs text-ink-3')}
                        data-shatter
                      >
                        {t('recoveryHint')}
                      </p>
                      <p
                        {...blur(850, 'mt-4 rounded-input bg-accent-2-soft px-3 py-2 text-xs text-ink-2')}
                        data-shatter
                      >
                        {t('credentialWarning')}
                      </p>
                    </>
                  )}

                  {error && (
                    <p
                      key={`${error}-${shake}`}
                      className="lm-error-slide mt-3 text-sm text-danger"
                    >
                      {error}
                    </p>
                  )}
                  {notice && (
                    <p className="lm-error-slide mt-3 text-sm text-accent">
                      {notice}
                    </p>
                  )}

                  <div {...materialize(450)}>
                    <button
                      type="submit"
                      disabled={submitting}
                      className={initialized ? primaryBtnCls : goldBtnCls}
                      data-shatter
                    >
                      {submitting
                        ? t('submitting')
                        : initialized
                          ? t('login')
                          : t('setup')}
                    </button>
                  </div>
                  {initialized && recoveryMethods.length > 0 && (
                    <div {...materialize(560)}>
                      <button
                        type="button"
                        className={linkBtnCls}
                        onClick={openRecover}
                      >
                        {t('forgotPassword')}
                      </button>
                    </div>
                  )}
                </form>
              )}
            </div>
          </div>
        )}
      </div>

      {phase === 'shatter' && (
        <ShatterCanvas onDone={() => setPhase('warp')} />
      )}
      {phase === 'warp' && <WarpCanvas onDone={enterHome} />}
    </div>
  )
}
