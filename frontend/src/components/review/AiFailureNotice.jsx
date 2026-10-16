import { useState } from 'react'
import { useLang } from '../../i18n'

/**
 * AI 生成失败提示：与 AI 掉线弹窗同款逻辑——顶部居中、红色、不自动消失。
 * 重试由调用方闭包提供（成功时调用方自行清除 failure）；取消仅关闭提示。
 */
export default function AiFailureNotice({ failure, onDismiss }) {
  const { t } = useLang()
  const [busy, setBusy] = useState(false)
  if (!failure) return null
  return (
    <div className="fixed left-1/2 top-4 z-50 flex max-w-[92vw] -translate-x-1/2 items-center rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 shadow-lg">
      <span className="shrink-0 font-semibold">{t('aiGenerateFailed')}</span>
      <span className="ml-2">{failure.message}</span>
      <button
        type="button"
        className="ml-3 shrink-0 rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-100 disabled:opacity-50"
        disabled={busy}
        onClick={async () => {
          setBusy(true)
          try {
            await failure.retry()
          } finally {
            setBusy(false)
          }
        }}
      >
        {busy ? t('retrying') : t('retry')}
      </button>
      <button
        type="button"
        className="ml-2 shrink-0 rounded border border-red-300 px-2 py-0.5 text-xs hover:bg-red-100"
        onClick={onDismiss}
      >
        {t('cancel')}
      </button>
    </div>
  )
}
