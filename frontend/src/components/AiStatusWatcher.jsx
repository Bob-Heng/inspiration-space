import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useLang } from '../i18n'

const POLL_MS = 30_000

/**
 * AI 服务状态监听：每 30s 探测一次 /api/ai/status。
 * 转离线（含首次检测即离线）→ 顶部红色弹窗，手动关闭；一次掉线只弹一次。
 * 转在线 → 顶部绿色提示 5s 自动消失，并触发译文/标题补全。
 * 未登录或请求失败时静默。
 */
export default function AiStatusWatcher() {
  const { t } = useLang()
  const [offlineVisible, setOfflineVisible] = useState(false)
  const [onlineVisible, setOnlineVisible] = useState(false)
  const offlineRef = useRef(false) // 上一拍是否离线（初始 unknown 视为在线）

  useEffect(() => {
    let cancelled = false
    let timer = null

    async function check() {
      try {
        const d = await api.getAiStatus()
        if (cancelled) return
        if (d.available) {
          if (offlineRef.current) {
            setOnlineVisible(true)
            api.reconcileAi().catch(() => {})
          }
          offlineRef.current = false
          setOfflineVisible(false)
        } else {
          if (!offlineRef.current) setOfflineVisible(true)
          offlineRef.current = true
        }
      } catch {
        // 未登录 / 后端不可达：静默
      }
      if (!cancelled) timer = setTimeout(check, POLL_MS)
    }

    check()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [])

  // 恢复提示 5s 自动消失
  useEffect(() => {
    if (!onlineVisible) return
    const timer = setTimeout(() => setOnlineVisible(false), 5000)
    return () => clearTimeout(timer)
  }, [onlineVisible])

  return (
    <>
      {offlineVisible && (
        <div className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-lg">
          <span className="font-semibold">{t('aiOfflineTitle')}</span>
          <span className="ml-2">{t('aiOfflineBody')}</span>
          <button
            type="button"
            className="ml-3 rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-100"
            onClick={() => setOfflineVisible(false)}
          >
            {t('aiOfflineDismiss')}
          </button>
        </div>
      )}
      {onlineVisible && (
        <div className="fixed left-1/2 top-4 z-50 -translate-x-1/2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700 shadow">
          {t('aiOnlineBack')}
        </div>
      )}
    </>
  )
}
