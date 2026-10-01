import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AiStatusWatcher from './components/AiStatusWatcher'
import RequireAuth from './components/RequireAuth'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
import ReviewPage from './pages/ReviewPage'
import ViewpointsPage from './pages/ViewpointsPage'

export default function App() {
  return (
    <BrowserRouter>
      <AiStatusWatcher />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<RequireAuth />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/viewpoints" element={<ViewpointsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
