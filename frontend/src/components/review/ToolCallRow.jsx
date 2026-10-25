import { useLang } from '../../i18n'

function StatusIcon({ status }) {
  if (status === 'running') {
    return (
      <span
        aria-hidden="true"
        className="h-3 w-3 shrink-0 animate-spin rounded-full border border-accent/30 border-t-accent"
      />
    )
  }
  if (status === 'completed') {
    return (
      <svg
        aria-hidden="true"
        className="h-3.5 w-3.5 shrink-0 text-accent"
        viewBox="0 0 16 16"
        fill="none"
      >
        <path d="m3 8.5 3 3 7-7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  return (
    <svg
      aria-hidden="true"
      className="h-3.5 w-3.5 shrink-0 text-danger"
      viewBox="0 0 16 16"
      fill="none"
    >
      <path d="M8 2.2 14 13H2L8 2.2Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M8 6v3.2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="8" cy="11.2" r="0.8" fill="currentColor" />
    </svg>
  )
}

export default function ToolCallRow({ toolCall }) {
  const { t, tf } = useLang()
  const status = toolCall.status
  const statusText = {
    running: t('toolQueryRunning'),
    completed: t('toolQueryCompleted'),
    failed: t('toolQueryFailed'),
  }[status]
  const targetText = tf('toolViewpointN', { id: toolCall.target })

  return (
    <div
      role="status"
      aria-atomic="true"
      className={`flex items-center gap-2 border-l-2 py-1 pl-3 text-xs ${
        status === 'failed' ? 'border-danger text-danger' : 'border-rule text-ink-2'
      }`}
    >
      <StatusIcon status={status} />
      <span>{statusText}</span>
      <span className={status === 'failed' ? 'text-danger' : 'text-ink'}>{targetText}</span>
    </div>
  )
}
