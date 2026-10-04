import { useEffect, useRef, useState } from 'react'

/* 发光边框描绘（参考 MotionVault glow-border-card 的光束概念，改为一次性描绘）：
 * 金色光束从左上角出发绕边框一周，所到之处留下边框；绕完后光束消失、边框保留。
 * 父元素需为 relative。active 为 true 后开始描绘；重新挂载可重播。
 */
export default function TracedBorder({
  active,
  radius = 20,
  delay = 0,
  duration = 1.5,
}) {
  const anchorRef = useRef(null)
  const [size, setSize] = useState(null)

  useEffect(() => {
    const parent = anchorRef.current?.parentElement
    if (!parent) return undefined
    const ro = new ResizeObserver(() => {
      const r = parent.getBoundingClientRect()
      setSize({ w: r.width, h: r.height })
    })
    ro.observe(parent)
    return () => ro.disconnect()
  }, [])

  const ready = active && size && size.w > 4 && size.h > 4
  const r = Math.min(radius, (size?.w ?? 0) / 2 - 2, (size?.h ?? 0) / 2 - 2)
  // 从左上角出发、顺时针一圈的圆角矩形路径（viewBox 含 2px 出血）
  const path =
    ready &&
    `M 2 ${2 + r} A ${r} ${r} 0 0 1 ${2 + r} 2 H ${size.w + 2 - r} A ${r} ${r} 0 0 1 ${size.w + 2} ${2 + r} V ${size.h + 2 - r} A ${r} ${r} 0 0 1 ${size.w + 2 - r} ${size.h + 2} H ${2 + r} A ${r} ${r} 0 0 1 2 ${size.h + 2 - r} Z`

  return (
    <span
      ref={anchorRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0"
    >
      {ready && (
        <svg
          className="lm-trace"
          viewBox={`0 0 ${size.w + 4} ${size.h + 4}`}
          style={{ '--d': `${delay}ms`, '--td': `${duration}s` }}
        >
          <path
            className="lm-trace-base"
            d={path}
            pathLength={100}
            fill="none"
            stroke="var(--color-rule)"
            strokeWidth={1.5}
          />
          <path
            className="lm-trace-tip"
            d={path}
            pathLength={100}
            fill="none"
            stroke="var(--color-accent-2)"
            strokeWidth={3}
            strokeLinecap="round"
            style={{ filter: 'blur(1px)' }}
          />
        </svg>
      )}
    </span>
  )
}
