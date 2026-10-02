import { useCallback, useEffect, useState } from 'react'

function Chevron({ up }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {up ? <path d="m5 15 7-7 7 7" /> : <path d="m19 9-7 7-7-7" />}
    </svg>
  )
}

/**
 * 悬浮"电梯"按钮：左=回顶部，右=到底部，平滑滚动动画（不超过 2s）。
 * target：'window' 或一个可滚动元素的 ref。
 * inline=true 时不做 fixed 定位（由父容器决定位置，如 sticky）。
 */
export default function ScrollElevator({ target = 'window', inline = false, className = '' }) {
  const [visible, setVisible] = useState(false)

  const getScroller = useCallback(() => {
    if (target === 'window') return null
    return target?.current ?? null
  }, [target])

  useEffect(() => {
    const scroller = getScroller()
    const el = scroller ?? document.documentElement
    const check = () => setVisible(el.scrollHeight > el.clientHeight + 40)
    check()
    const listener = scroller ?? window
    listener.addEventListener('scroll', check, { passive: true })
    window.addEventListener('resize', check)
    return () => {
      listener.removeEventListener('scroll', check)
      window.removeEventListener('resize', check)
    }
  }, [getScroller])

  function animatedScroll(toTop) {
    const scroller = getScroller()
    const el = scroller ?? document.documentElement
    const from = scroller ? scroller.scrollTop : window.scrollY
    const to = toTop ? 0 : el.scrollHeight - el.clientHeight
    const distance = Math.abs(to - from)
    if (distance < 4) return
    const duration = Math.min(1800, Math.max(500, distance * 0.4))
    const start = performance.now()
    const ease = (k) => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2)
    function step(now) {
      const k = Math.min(1, (now - start) / duration)
      const y = from + (to - from) * ease(k)
      if (scroller) scroller.scrollTop = y
      else window.scrollTo(0, y)
      if (k < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }

  if (!visible) return null

  return (
    <div
      className={
        (inline ? '' : 'fixed bottom-6 right-6 z-40 ') +
        `flex flex-row gap-2 ${className}`
      }
    >
      <button
        type="button"
        aria-label="回到顶部"
        title="回到顶部"
        className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-800 text-white shadow-lg hover:bg-slate-700"
        onClick={() => animatedScroll(true)}
      >
        <Chevron up />
      </button>
      <button
        type="button"
        aria-label="来到底部"
        title="来到底部"
        className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-800 text-white shadow-lg hover:bg-slate-700"
        onClick={() => animatedScroll(false)}
      >
        <Chevron up={false} />
      </button>
    </div>
  )
}
