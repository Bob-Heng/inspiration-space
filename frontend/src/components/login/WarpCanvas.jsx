import { useEffect, useRef } from 'react'

/* 星空穿梭（参考 MotionVault starfield，2D canvas 实现）+ 不规则白色绽放：
 *   0~0.35s   画面由白渐入深空（logo 的夜空靛蓝），星星随背景变暗显现
 *   0.35~1.5s 纯星空穿梭
 *   1.5~2.5s  白色从画面中心向外不规则扩散（非圆形：极坐标叠加三组正弦扰动），
 *             高斯模糊羽化——扩散带内黑白连续过渡，每个点渐渐变白；
 *             星星被白色吞没，最终完全融入白底
 * 结束后 onDone（跳转首页）。
 */
const DEEP = [22, 24, 56] // 深空靛蓝（logo 夜空）
const PAPER = [253, 252, 249] // 纸面白
const STAR_COLORS = ['#ffffff', '#ffffff', '#ffffff', '#9db4ff', '#f0c14b']
const STAR_COUNT = 380
// 前 1.5s 纯星空穿梭，后 1s 由黑变白（用户明确时序）
const BLOOM_AT = 1.5
const DURATION = 2.5
// 不规则形状：三组固定相位的正弦扰动
const LOBES = [
  [3, 1.3, 0.2],
  [5, 4.2, 0.14],
  [8, 2.1, 0.09],
]

function lerp(a, b, k) {
  return a + (b - a) * k
}

export default function WarpCanvas({ onDone }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
    const w = window.innerWidth
    const h = window.innerHeight
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)
    const cx = w / 2
    const cy = h / 2
    const maxR = Math.hypot(cx, cy)

    const stars = Array.from({ length: STAR_COUNT }, () => ({
      a: Math.random() * Math.PI * 2,
      r: 4 + Math.random() * maxR,
      v: 60 + Math.random() * 120,
      size: 0.6 + Math.random() * 1.6,
      color: STAR_COLORS[(Math.random() * STAR_COLORS.length) | 0],
    }))

    function shapeFactor(theta) {
      let f = 1
      for (const [k, phase, amp] of LOBES) f += amp * Math.sin(k * theta + phase)
      return f
    }

    // 白色绽放：屏外画布绘制不规则形状，高斯模糊羽化 + 实心内核叠回。
    // 扩散带内黑白连续过渡——没有可见分界线；每个点随前缘推进渐渐变白
    const bloom = document.createElement('canvas')
    bloom.width = w
    bloom.height = h
    const bctx = bloom.getContext('2d')

    function drawBloom(R) {
      bctx.clearRect(0, 0, w, h)
      bctx.beginPath()
      for (let i = 0; i <= 96; i += 1) {
        const theta = (i / 96) * Math.PI * 2
        const rr = R * shapeFactor(theta)
        const x = cx + rr * Math.cos(theta)
        const y = cy + rr * Math.sin(theta)
        if (i === 0) bctx.moveTo(x, y)
        else bctx.lineTo(x, y)
      }
      bctx.closePath()
      bctx.fillStyle = `rgb(${PAPER[0]}, ${PAPER[1]}, ${PAPER[2]})`
      bctx.fill()
      // 仅高斯模糊层，不叠实心内核：内核的硬边会在光晕中形成可见分界。
      // 模糊半径随扩散增大，扩散带内黑白完全连续过渡
      ctx.save()
      ctx.filter = `blur(${Math.min(32 + R * 0.18, 110)}px)`
      ctx.drawImage(bloom, 0, 0)
      ctx.restore()
    }

    let raf
    let start
    let last
    function tick(now) {
      if (start === undefined) start = last = now
      const dt = Math.min((now - last) / 1000, 0.05)
      last = now
      const t = Math.min((now - start) / 1000, DURATION)

      // 背景：白 → 深空（0.35s 渐隐）
      const bgK = Math.min(t / 0.35, 1)
      ctx.fillStyle = `rgb(${Math.round(lerp(PAPER[0], DEEP[0], bgK))}, ${Math.round(lerp(PAPER[1], DEEP[1], bgK))}, ${Math.round(lerp(PAPER[2], DEEP[2], bgK))})`
      ctx.fillRect(0, 0, w, h)

      // 星星：随背景变暗而显现；穿梭加速
      const starAlpha = Math.min(t / 0.3, 1)
      const speedRamp = 1 + t * 0.8
      for (const s of stars) {
        const r0 = s.r
        s.r += s.v * dt * speedRamp * (0.3 + (s.r / maxR) * 2.2)
        if (s.r > maxR) {
          s.r = 2 + Math.random() * 8
          s.a = Math.random() * Math.PI * 2
          continue
        }
        const x0 = cx + r0 * Math.cos(s.a)
        const y0 = cy + r0 * Math.sin(s.a)
        const x1 = cx + s.r * Math.cos(s.a)
        const y1 = cy + s.r * Math.sin(s.a)
        ctx.strokeStyle = s.color
        ctx.globalAlpha = starAlpha * Math.min(0.25 + (s.r / maxR), 1)
        ctx.lineWidth = s.size * (0.4 + (s.r / maxR) * 1.2)
        ctx.lineCap = 'round'
        ctx.beginPath()
        ctx.moveTo(x0, y0)
        ctx.lineTo(x1, y1)
        ctx.stroke()
      }
      ctx.globalAlpha = 1

      // 白色绽放：easeInOut 由中心向外，不规则前缘
      if (t > BLOOM_AT) {
        const u = Math.min((t - BLOOM_AT) / (DURATION - BLOOM_AT), 1)
        const eased = u * u * (3 - 2 * u)
        drawBloom(eased * maxR * 1.3)
      }

      if (t < DURATION) {
        raf = requestAnimationFrame(tick)
      } else {
        onDone?.()
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [onDone])

  return <canvas ref={canvasRef} className="lm-fx-canvas" aria-hidden="true" />
}
