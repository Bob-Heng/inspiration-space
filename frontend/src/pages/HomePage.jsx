import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import InspirationPanel from '../components/InspirationPanel'
import ScrollElevator from '../components/ScrollElevator'
import { usePageHeader } from '../header'
import { LangSelect, useLang } from '../i18n'

/* 首页入场（rAF 绝对时间驱动）：
 *   0~68%    平移：整页倾斜 24° + 0.8 倍 + 大圆角，从屏底只露 1/5 头
 *            平移到旋转起点（慢→快→慢，ease-in-out）
 *   68~84%   旋转：24° → 0°（ease-out，非线性）
 *   84~100%  放大：0.8 → 1（ease-out，非线性）
 *   +0.4s    圆角展开：大圆角逐渐变淡、向外侧展开，最终收成窗口直角
 * 主体 1.0s（?slowhome 演示时为 5s）+ 圆角展开 0.4s。 */

const MOVE_END = 0.68
const ROT_END = 0.84
const TILT_DEG = 24
const ENTER_SCALE = 0.8
const ENTER_RADIUS = 48
const RADIUS_FADE_MS = 400

const easeInOutCubic = (k) =>
  k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2
const easeOutCubic = (k) => 1 - (1 - k) ** 3

export default function HomePage() {
  const navigate = useNavigate()
  const { t } = useLang()
  const [enter] = useState(
    () => sessionStorage.getItem('inspiration_entry') === 'warp',
  )
  // 调试用：?slowhome 将入场动画放慢到 5s（验收动画用）
  const slowHome =
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).has('slowhome')
  const rootRef = useRef(null)

  useEffect(() => {
    if (!enter) return undefined
    sessionStorage.removeItem('inspiration_entry')
    const el = rootRef.current
    if (!el) return undefined
    const dur = slowHome ? 5000 : 1000
    // 轴心取视口底边而非元素底边：页面有几千像素高，绕元素底边旋转时
    // 可见区域只做平移、旋转不可见（此前"摊平看不见"的根因）
    el.style.transformOrigin = '50% 100vh'
    el.style.willChange = 'transform, opacity'
    el.style.overflow = 'hidden'
    el.style.boxShadow = '0 24px 64px -16px rgb(70 80 140 / 0.35)'
    let raf
    let start
    function tick(now) {
      if (start === undefined) start = now
      const t = Math.min((now - start) / dur, 1)
      let rx = TILT_DEG
      let s = ENTER_SCALE
      let y = 0
      let o = 1
      let radius = ENTER_RADIUS // 平移/旋转/放大全程保持大圆角
      if (t < MOVE_END) {
        // 平移：从屏底只露 1/5 头（页顶位于 80% 视口高）到旋转起点，慢→快→慢
        const k = easeInOutCubic(t / MOVE_END)
        y = window.innerHeight * 0.8 * (1 - k) + 24 * k
        o = Math.min(t / 0.08, 1)
      } else if (t < ROT_END) {
        // 旋转放平（非线性）
        const k = easeOutCubic((t - MOVE_END) / (ROT_END - MOVE_END))
        y = 24 * (1 - k)
        rx = TILT_DEG * (1 - k)
      } else if (t < 1) {
        // 放大贴合（非线性）
        const k = easeOutCubic((t - ROT_END) / (1 - ROT_END))
        y = 0
        rx = 0
        s = ENTER_SCALE + (1 - ENTER_SCALE) * k
      } else {
        // 放大完成后：圆角逐渐变淡并向外侧展开，最终变成窗口直角
        rx = 0
        s = 1
        const k = easeInOutCubic(
          Math.min((now - start - dur) / RADIUS_FADE_MS, 1),
        )
        radius = ENTER_RADIUS * (1 - k)
        el.style.boxShadow = `0 24px 64px -16px rgb(70 80 140 / ${0.35 * (1 - k)})`
      }
      el.style.opacity = String(o)
      el.style.transform = `perspective(900px) rotateX(${rx}deg) translateY(${y}px) scale(${s})`
      el.style.borderRadius = `${Math.max(radius, 0)}px`
      if (now - start < dur + RADIUS_FADE_MS) {
        raf = requestAnimationFrame(tick)
      } else {
        el.style.opacity = ''
        el.style.transform = ''
        el.style.willChange = ''
        el.style.overflow = ''
        el.style.borderRadius = ''
        el.style.boxShadow = ''
      }
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      el.style.opacity = ''
      el.style.transform = ''
      el.style.willChange = ''
      el.style.overflow = ''
      el.style.borderRadius = ''
      el.style.boxShadow = ''
    }
  }, [enter, slowHome])

  const handleLogout = useCallback(async () => {
    await api.logout().catch(() => {})
    navigate('/login', { replace: true })
  }, [navigate])

  const headerItems = useMemo(
    () => [
      {
        hk: 'logout',
        node: (
          <button className="ui-link text-sm" onClick={handleLogout}>
            {t('logout')}
          </button>
        ),
      },
      { hk: 'lang', node: <LangSelect /> },
    ],
    [t, handleLogout],
  )
  usePageHeader({ current: 'home', subtitle: t('home'), items: headerItems })

  return (
    <div ref={rootRef} className="min-h-screen bg-paper">
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
