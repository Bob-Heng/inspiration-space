import { useEffect, useMemo, useRef } from 'react'

/* 立体滚动卡墙（登录开场）。
 * 时序（参考 MotionVault marquee-3d，速度曲线按需求定制）：
 *   A 段 0~0.9s  快速：首卡从进入屏幕到完全离开
 *   B 段 0.9~2.4s 慢速：默认速度，末卡在本段末尾恰好进入屏幕
 *   C 段 2.4~3.4s 快速：全部卡片完全离开屏幕
 * 三段速度在交界处用 smoothstep 平滑过渡（对称混合，积分不变，时序精确）。
 * 每列卡片数 n 由时间推算：慢速段末列头位移须恰好等于 (n-1)×卡片间距。
 */
const CARD_H = 132
const GAP = 18
const PITCH = CARD_H + GAP
const T_A = 0.9
const T_B = 1.5
const T_C = 1.0
const BLEND = 0.18 // 速度混合窗口（秒），对称于段边界
// 四个完美数（用户指定）：同列按 (列号+序号)%4 轮转，保证同列不相邻同号
const PERFECTS = [6, 28, 496, 8128]
const COL_LEFT = ['3%', '27%', '52%', '77%']
const COL_DEPTH = [0, 28, -16, 12] // translateZ 视差

export default function CardWall({ onLastCardCenter, onDone, timeScale = 1 }) {
  const innerRefs = useRef([])
  // 回调经 ref 取用：父组件重渲染不得重启卡墙（整场只跑一次）
  const cbRef = useRef({ onLastCardCenter, onDone })
  useEffect(() => {
    cbRef.current = { onLastCardCenter, onDone }
  }, [onLastCardCenter, onDone])

  const geo = useMemo(() => {
    const h = window.innerHeight
    const tA = T_A * timeScale
    const tB = T_B * timeScale
    const tC = T_C * timeScale
    const vA = (h + CARD_H) / tA // 快段速度：首卡 0.9s 穿越全屏
    // 卡片数：慢速段结束时位移 (n-1)*PITCH，须覆盖 A 段位移 + B 段 0.42 屏
    const n = Math.ceil((h + CARD_H + 0.42 * h) / PITCH) + 1
    const dAB = (n - 1) * PITCH
    const vB = (dAB - vA * tA) / tB // 慢段速度（由 n 反推，保证末卡准点入场）
    const vC = vA // 离场与入场同速
    // 末卡中心到达屏幕中心时的位移（上下方向对称，两向同值）
    const posTrigger = dAB + (h + CARD_H) / 2
    const Hc = n * PITCH - GAP // 列总高
    const blend = BLEND * timeScale // 速度混合窗口
    return { h, n, dAB, vA, vB, vC, tA, tB, posTrigger, Hc, blend, total: tA + tB + tC }
  }, [timeScale])

  useEffect(() => {
    const { h, vA, vB, vC, tA, tB, Hc, posTrigger, blend, total } = geo
    // 位移对时间解析求值（非逐帧积分）：后台标签页 rAF 被节流时也能跳到正确位置
    const a0 = tA - blend
    const a1 = tA + blend
    const b0 = tA + tB - blend
    const b1 = tA + tB + blend
    const pA0 = vA * a0
    const pA1 = pA0 + blend * (vA + vB)
    const pB0 = pA1 + vB * (b0 - a1)
    const pB1 = pB0 + blend * (vB + vC)
    // 段边界处速度的 smoothstep 混合，积分解析式：∫0^u (3x²-2x³)dx = u³ - 0.5u⁴
    const blendPos = (p0, vFrom, vTo, t0, t) => {
      const u = (t - t0) / (2 * blend)
      return p0 + vFrom * (t - t0) + (vTo - vFrom) * 2 * blend * (u ** 3 - 0.5 * u ** 4)
    }
    function posAt(t) {
      if (t <= a0) return vA * t
      if (t <= a1) return blendPos(pA0, vA, vB, a0, t)
      if (t <= b0) return pA1 + vB * (t - a1)
      if (t <= b1) return blendPos(pB0, vB, vC, b0, t)
      return pB1 + vC * (t - b1)
    }
    let raf
    let start
    let fired = false
    function tick(now) {
      if (start === undefined) start = now
      const t = (now - start) / 1000
      const pos = posAt(t)
      for (let i = 0; i < 4; i += 1) {
        const el = innerRefs.current[i]
        if (!el) continue
        // 偶数列向上（首卡自下方入场），奇数列向下（首卡自上方入场）
        const y = i % 2 === 0 ? h - pos : -Hc + pos
        el.style.transform = `translate3d(0, ${y}px, 0)`
      }
      if (!fired && pos >= posTrigger) {
        fired = true
        cbRef.current.onLastCardCenter?.()
      }
      if (t < total) {
        raf = requestAnimationFrame(tick)
      } else {
        cbRef.current.onDone?.()
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [geo])

  return (
    <div className="lm-wall" aria-hidden="true">
      <div className="lm-wall-plane">
        {COL_LEFT.map((left, i) => {
          const up = i % 2 === 0
          // 向上列：0 号卡在最上方（领队）；向下列：0 号卡在最下方（领队）
          const order = Array.from({ length: geo.n }, (_, k) =>
            up ? k : geo.n - 1 - k,
          )
          return (
            <div
              key={i}
              className="lm-wall-col"
              style={{
                left,
                width: 'min(21vw, 240px)',
                transform: `translateZ(${COL_DEPTH[i]}px)`,
              }}
            >
              <div
                ref={(el) => {
                  innerRefs.current[i] = el
                }}
                className="lm-wall-col-inner"
              >
                {order.map((k) => (
                  <div key={k} className="lm-wall-card">
                    <span className="lm-wall-id">
                      #{PERFECTS[(i + k) % PERFECTS.length]}
                    </span>
                    <span className="lm-wall-bar lm-wall-bar--short" />
                    <span className="lm-wall-bar lm-wall-bar--gold" />
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
