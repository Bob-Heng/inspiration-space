import { useEffect, useRef, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AiStatusWatcher from './components/AiStatusWatcher'
import RequireAuth from './components/RequireAuth'
import { HeaderProvider } from './header'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
import ReviewPage from './pages/ReviewPage'
import ViewpointsPage from './pages/ViewpointsPage'

/* 页面切换过渡：旧页面向下淡出 0.8s → 新页面向上淡入 0.8s（见 tokens.css .pt-out/.pt-in）。
 * 淡出态由 location 与 displayed 的路径差派生（不在 effect 里同步 setState）；
 * 登录穿梭进首页跳过：首页自带摊平入场。仅路径变化触发切换动画；
 * 同路径的查询参数变化立即同步 displayed（react-router 的 <Routes location> 会让子树
 * useLocation/useSearchParams 读到 displayed 而非实时地址，不同步则队列点击失效）。 */
function AnimatedRoutes() {
  const location = useLocation()
  const [displayed, setDisplayed] = useState(location)
  // 淡入类只挂一个动画周期：播完即摘除，保证下次淡出从自然样式触发 transition。
  // 摘除定时器放 ref 且不被 effect 清理误杀（否则 pt-in 残留：容器成为 fixed 包含块
  // 且后续淡出 transition 从动画填充态出发被 Chrome 跳过）
  const [fadingIn, setFadingIn] = useState(false)
  const fadeInTimer = useRef(null)
  const isSame = location.pathname === displayed.pathname

  // 仅组件卸载时清理摘除定时器
  useEffect(
    () => () => clearTimeout(fadeInTimer.current),
    [],
  )

  useEffect(() => {
    if (isSame) {
      if (location !== displayed) {
        const id = setTimeout(() => setDisplayed(location), 0)
        return () => clearTimeout(id)
      }
      return undefined
    }
    const warp = sessionStorage.getItem('inspiration_entry') === 'warp'
    // 淡出 0.6s → 间隔 0.2s → 换入新页面再淡入 0.6s（由快变慢）
    const t1 = setTimeout(
      () => {
        setDisplayed(location)
        if (!warp) {
          setFadingIn(true)
          clearTimeout(fadeInTimer.current)
          fadeInTimer.current = setTimeout(() => setFadingIn(false), 650)
        }
      },
      warp ? 0 : 800,
    )
    return () => clearTimeout(t1)
  }, [isSame, location, displayed])

  return (
    <div className={!isSame ? 'pt-out' : fadingIn ? 'pt-in' : ''}>
      <Routes location={displayed}>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/viewpoints" element={<ViewpointsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <HeaderProvider>
        <AiStatusWatcher />
        <AnimatedRoutes />
      </HeaderProvider>
    </BrowserRouter>
  )
}
