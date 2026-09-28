import { useEffect, useRef, useState } from 'react'
import TranslatedText from '../TranslatedText'
import { useLang } from '../../i18n'

export default function DiscussionCard({ session, sending, onSend }) {
  const { t, tf } = useLang()
  const [draft, setDraft] = useState('')
  const [copiedId, setCopiedId] = useState(null)
  const listRef = useRef(null)
  const active = session?.status === 'active'
  const messages = session?.messages ?? []

  // 只在讨论容器内滚动，不再牵动整个页面（scrollIntoView 会把页面顶到 AI 回复底部）
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages.length, sending])

  async function handleCopy(msg) {
    try {
      await navigator.clipboard.writeText(msg.content)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = msg.content
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      ta.remove()
    }
    setCopiedId(msg.id)
    setTimeout(() => setCopiedId(null), 1500)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const content = draft.trim()
    if (!content || !active || sending) return
    const ok = await onSend(content)
    if (ok) setDraft('')
  }

  return (
    <div className="rounded-lg bg-white p-4 shadow">
      <h2 className="text-sm font-bold text-slate-800">{t('discussion')}</h2>

      <div ref={listRef} className="mt-3 max-h-96 space-y-3 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <p className="py-4 text-center text-sm text-slate-400">
            {t('discussionEmpty')}
          </p>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-slate-800 text-white'
                  : 'bg-slate-100 text-slate-800'
              }`}
            >
              <div className="mb-0.5 flex items-center gap-2">
                <p
                  className={`text-xs ${
                    msg.role === 'user' ? 'text-slate-300' : 'text-slate-400'
                  }`}
                >
                  {msg.role === 'user' ? t('me') : t('ai')}
                </p>
                {msg.role !== 'user' && (
                  <button
                    type="button"
                    className="text-xs text-slate-400 hover:text-slate-700"
                    onClick={() => handleCopy(msg)}
                  >
                    {copiedId === msg.id ? t('copied') : t('copy')}
                  </button>
                )}
              </div>
              <p className="whitespace-pre-wrap">
                <TranslatedText
                  contentZh={msg.content_zh ?? msg.content}
                  contentEn={msg.content_en ?? msg.content}
                  originalLang={msg.original_lang}
                />
              </p>
            </div>
          </div>
        ))}
        {sending && <p className="text-center text-xs text-slate-400">{t('thinking')}</p>}
      </div>

      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <textarea
          className="flex-1 rounded border border-slate-300 p-2 text-sm outline-none focus:border-slate-500 disabled:bg-slate-50"
          rows={2}
          placeholder={active ? t('inputPlaceholder') : t('sessionClosed')}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!active || sending}
        />
        <button
          type="submit"
          className="self-end rounded bg-slate-800 px-4 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
          disabled={!active || sending || !draft.trim()}
        >
          {sending ? t('sending') : t('send')}
        </button>
      </form>
      {!active && (
        <p className="mt-2 text-xs text-slate-400">
          {tf('sessionStatus', { status: session?.status })}
        </p>
      )}
    </div>
  )
}
