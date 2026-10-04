import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useLang } from '../i18n'

const NAV = [
  { key: 'home', to: '/', labelKey: 'home' },
  { key: 'review', to: '/review', labelKey: 'reviewWorkbench' },
  { key: 'viewpoints', to: '/viewpoints', labelKey: 'viewpointLibrary' },
]

// 跨页面记住金色下标位置（页头随路由切换重挂载，位置在模块作用域保持连续：
// 连续点击不同页面时，下标从当前位置继续向新目标移动，不重启）
let indicatorCache = null // { left }（px，相对 nav 容器）

/**
 * 统一页头：灵感空间 + 大斜杠 + 副标题（略小、略淡、位置更靠下且与标题交错）。
 * 导航固定为 首页/审议工作台/观点库，位置跨页一致（当前页高亮不可点，
 * 金色下标在非线性缓动中滑向当前页）；页面特有按钮放右侧固定宽度区，
 * 不影响导航位置；语言切换恒为 extras 最右元素，跨页位置一致。
 */
export default function PageHeader({ current, subtitle, slogan = null, extras = null }) {
  const { t, lang } = useLang()
  const navRef = useRef(null)
  const itemRefs = useRef({})
  const indRef = useRef(null)

  useEffect(() => {
    const nav = navRef.current
    const target = itemRefs.current[current]
    const ind = indRef.current
    if (!nav || !target || !ind) return undefined
    const navBox = nav.getBoundingClientRect()
    const box = target.getBoundingClientRect()
    const to = box.left - navBox.left + box.width / 2 - 8
    const from = indicatorCache ?? to
    const dur = 320
    let raf
    let start
    function tick(now) {
      if (start === undefined) start = now
      const k = Math.min((now - start) / dur, 1)
      // easeInOutCubic：速度非线性（慢→快→慢）
      const e = k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2
      ind.style.left = `${from + (to - from) * e}px`
      if (k < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        indicatorCache = to
      }
    }
    ind.style.left = `${from}px`
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [current, lang])

  return (
    <header className="shrink-0 border-b border-rule bg-white">
      <div className="mx-auto flex max-w-7xl items-center px-4 py-3">
        <div className="flex items-start">
          <h1 className="font-display text-lg font-semibold leading-none tracking-tight text-ink">
            {t('appName')}
          </h1>
          <span
            aria-hidden
            className="-ml-0.5 -mt-1 text-[34px] font-light leading-none text-ink-3"
          >
            /
          </span>
          <span className="-ml-1 mt-4 text-xs leading-none text-ink-2">
            {subtitle}
          </span>
        </div>
        {slogan && (
          <div className="min-w-0 flex-1 truncate whitespace-nowrap px-4 text-center text-base text-ink-3">
            {slogan}
          </div>
        )}
        <nav ref={navRef} className="relative ml-auto flex items-center gap-4">
          {NAV.map((item) =>
            item.key === current ? (
              <span
                key={item.key}
                ref={(el) => {
                  itemRefs.current[item.key] = el
                }}
                className="text-sm font-medium text-ink"
              >
                {t(item.labelKey)}
              </span>
            ) : (
              <Link
                key={item.key}
                ref={(el) => {
                  itemRefs.current[item.key] = el
                }}
                to={item.to}
                className="text-sm text-ink-2 transition-colors duration-200 hover:text-ink"
              >
                {t(item.labelKey)}
              </Link>
            ),
          )}
          {/* 页面特有按钮的固定宽度区：导航三键跨页位置不动；内容单行不换行 */}
          <div className="flex w-[28rem] items-center justify-end gap-3 whitespace-nowrap">
            {extras}
          </div>
          <span
            ref={indRef}
            aria-hidden
            className="absolute -bottom-1.5 h-[3px] w-4 rounded-full bg-accent-2"
          />
        </nav>
      </div>
    </header>
  )
}
