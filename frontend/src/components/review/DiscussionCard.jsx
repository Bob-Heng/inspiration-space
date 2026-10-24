import { useEffect, useRef, useState } from 'react'
import TranslatedText from '../TranslatedText'
import { useLang } from '../../i18n'
import ToolCallRow from './ToolCallRow'
import { buildDiscussionTimeline } from './discussionTimeline'

export default function DiscussionCard({
  session,
  toolCalls = [],
  sending,
  onSend,
  phase = 'polish',
  onEnterPolish,
}) {
  const { t, tf } = useLang()
  const [draft, setDraft] = useState('')
  const [copiedId, setCopiedId] = useState(null)
  const listRef = useRef(null)
  const active = session?.status === 'active'
  const messages = session?.messages ?? []
  const timeline = buildDiscussionTimeline(messages, toolCalls)

  // 只在讨论容器内滚动，不再牵动整个页面（scrollIntoView 会把页面顶到 AI 回复底部）
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [messages.length, sending, timeline.length])

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
    <div className="ui-card p-4">
      <div className="flex items-center">
        <h2 className="text-sm font-bold text-ink">{t('discussion')}</h2>
        {phase === 'distill' && active && (
          <button
            type="button"
            className="ui-btn-ghost ml-auto px-2 py-1 text-xs"
            onClick={onEnterPolish}
          >
            {t('enterPolish')}
          </button>
        )}
      </div>

      <div ref={listRef} className="mt-3 max-h-96 space-y-3 overflow-y-auto pr-1">
        {timeline.length === 0 && (
          <p className="py-4 text-center text-sm text-ink-3">
            {t('discussionEmpty')}
          </p>
        )}
        {timeline.map((item) =>
          item.type === 'tool' ? (
            <ToolCallRow key={item.key} toolCall={item.toolCall} />
          ) : (
            <div
              key={item.key}
              className={`flex ${item.message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  item.message.role === 'user'
                    ? 'bg-ink text-accent-ink'
                    : 'bg-paper-2 text-ink'
                }`}
              >
                <div className="mb-0.5 flex items-center gap-2">
                  <p
                    className={`text-xs ${
                      item.message.role === 'user' ? 'text-accent-ink/60' : 'text-ink-3'
                    }`}
                  >
                    {item.message.role === 'user' ? t('me') : t('ai')}
                  </p>
                  {item.message.role !== 'user' && (
                    <button
                      type="button"
                      className="ui-link text-xs"
                      onClick={() => handleCopy(item.message)}
                    >
                      {copiedId === item.message.id ? t('copied') : t('copy')}
                    </button>
                  )}
                </div>
                <p className="whitespace-pre-wrap">
                  <TranslatedText
                    contentZh={item.message.content_zh}
                    contentEn={item.message.content_en}
                    originalLang={item.message.original_lang}
                  />
                </p>
              </div>
            </div>
          ),
        )}
        {sending && <p className="text-center text-xs text-ink-3">{t('thinking')}</p>}
      </div>

      <form onSubmit={handleSubmit} className="mt-3 flex gap-2">
        <textarea
          className="ui-input flex-1 p-2 text-sm disabled:bg-paper-2"
          rows={5}
          placeholder={active ? t('inputPlaceholder') : t('sessionClosed')}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={!active || sending}
        />
        <button
          type="submit"
          className="ui-btn-primary self-end px-4 py-2 text-sm"
          disabled={!active || sending || !draft.trim()}
        >
          {sending ? t('sending') : t('send')}
        </button>
      </form>
      {!active && (
        <p className="mt-2 text-xs text-ink-3">
          {tf('sessionStatus', { status: session?.status })}
        </p>
      )}
    </div>
  )
}
