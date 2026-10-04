import { useEffect, useRef } from 'react'

/* 粒子碎裂（参考 MotionVault 粒子 03 粒子文字的思路，去交互）：
 * 登录成功后，先把登录窗内容光栅化到屏外 canvas——逐行文本（Range.getClientRects
 * 拿到每个行片段的真实位置与计算样式）、输入框/登录窗外框（圆角描边）、按钮（胶囊
 * 填充 + 文字）——再按 GAP 网格采样像素，取真实颜色生成粒子，碎开后依旧认得出
 * 文字与边框形态。每个采样点沿垂直屏幕方向堆叠 LAYERS+1 层粒子（层间距 = 平面
 * 采样间距），飞行时深层粒子放大更快、径向视差更大，形成"厚度"。
 * 随后所有粒子加速飞向镜头（radial + 放大 + 淡出），时长 ~0.9s。
 */

const DURATION = 1.0
const GAP = 3 // 平面采样间距（px）；z 方向层间距与此相等
const LAYERS = 5 // 表层之外的堆叠层数
const DOT = 1.5 // 粒子基础尺寸（≈ GAP/2，密而不糊）

export default function ShatterCanvas({ onDone }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const w = window.innerWidth
    const h = window.innerHeight
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)
    const cx = w / 2
    const cy = h / 2

    const ruleColor =
      getComputedStyle(document.documentElement)
        .getPropertyValue('--color-rule')
        .trim() || '#d9d9e3'

    // ---- 1) 光栅化到屏外画布（CSS 像素坐标系） ----
    const off = document.createElement('canvas')
    off.width = w
    off.height = h
    const octx = off.getContext('2d', { willReadFrequently: true })

    function drawTextNode(node) {
      const range = document.createRange()
      range.selectNodeContents(node)
      const rects = [...range.getClientRects()].filter(
        (r) => r.width > 1 && r.height > 1,
      )
      if (!rects.length) return
      const cs = getComputedStyle(node.parentElement)
      octx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`
      octx.fillStyle = cs.color
      octx.textBaseline = 'middle'
      const text = node.textContent
      if (rects.length === 1) {
        octx.fillText(text, rects[0].left, rects[0].top + rects[0].height / 2)
        return
      }
      // 多行：按各行片段宽度占比切分子串（近似，足够保留字形轮廓）
      const totalW = rects.reduce((s, r) => s + r.width, 0)
      let offset = 0
      rects.forEach((r, i) => {
        const n =
          i === rects.length - 1
            ? text.length - offset
            : Math.round((r.width / totalW) * text.length)
        octx.fillText(text.slice(offset, offset + n), r.left, r.top + r.height / 2)
        offset += n
      })
    }

    function roundRectPath(c, r, radius) {
      c.beginPath()
      c.roundRect(r.left, r.top, r.width, r.height, Math.min(radius, r.height / 2))
    }

    for (const el of document.querySelectorAll('[data-shatter]')) {
      // 文本节点逐行绘制
      for (const node of el.childNodes) {
        if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
          drawTextNode(node)
        }
      }
      for (const child of el.querySelectorAll('span, p, h1')) {
        for (const node of child.childNodes) {
          if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
            drawTextNode(node)
          }
        }
      }
      // 按钮：胶囊填充 + 文字
      const btn = el.tagName === 'BUTTON' ? el : el.querySelector('button')
      if (btn) {
        const r = btn.getBoundingClientRect()
        const cs = getComputedStyle(btn)
        if (cs.backgroundColor && cs.backgroundColor !== 'rgba(0, 0, 0, 0)') {
          octx.fillStyle = cs.backgroundColor
          roundRectPath(octx, r, 999)
          octx.fill()
        }
        for (const node of btn.childNodes) {
          if (node.nodeType === Node.TEXT_NODE && node.textContent.trim()) {
            drawTextNode(node)
          }
        }
      }
    }
    // 边框：输入框与登录窗外框（圆角描边）
    for (const el of document.querySelectorAll('[data-shatter-box]')) {
      const r = el.getBoundingClientRect()
      if (r.width < 4 || r.height < 4) continue
      octx.strokeStyle = ruleColor
      octx.lineWidth = 1.5
      roundRectPath(octx, r, Number(el.dataset.shatterBox) || 12)
      octx.stroke()
    }

    // ---- 2) 采样生成粒子（含 z 向堆叠） ----
    const img = octx.getImageData(0, 0, w, h).data
    const particles = []
    for (let y = 0; y < h; y += GAP) {
      for (let x = 0; x < w; x += GAP) {
        const i = (y * w + x) * 4
        if (img[i + 3] <= 100) continue
        const color = `rgb(${img[i]}, ${img[i + 1]}, ${img[i + 2]})`
        const dx = x - cx
        const dy = y - cy
        const d = Math.hypot(dx, dy) || 1
        for (let z = 0; z <= LAYERS; z += 1) {
          particles.push({
            x,
            y,
            z,
            dx: dx / d,
            dy: dy / d,
            d0: d,
            speed: (140 + d * 0.9) * (0.75 + Math.random() * 0.5),
            color,
          })
        }
      }
    }

    // ---- 3) 扑面飞行 ----
    let raf
    let start
    function tick(now) {
      if (start === undefined) start = now
      const t = Math.min((now - start) / 1000, DURATION)
      ctx.clearRect(0, 0, w, h)
      for (const p of particles) {
        // 深层粒子：飞得稍快、放大稍多 → 层间拉开，形成厚度。
        // 整体速度压低、放大放缓：登录窗像从更远处缓缓扑到屏前（初始大小不变）
        const depth = 1 + p.z * 0.18
        const travel = p.speed * depth * t * t * 0.6
        const x = p.x + p.dx * travel
        const y = p.y + p.dy * travel
        const s = DOT * (1 + (1.2 + p.z * 0.25) * t * t)
        const alpha = t < 0.6 ? 1 : 1 - (t - 0.6) / (DURATION - 0.6)
        ctx.globalAlpha = Math.max(alpha, 0) * (1 - p.z * 0.12)
        ctx.fillStyle = p.color
        ctx.fillRect(x - s / 2, y - s / 2, s, s)
      }
      ctx.globalAlpha = 1
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
