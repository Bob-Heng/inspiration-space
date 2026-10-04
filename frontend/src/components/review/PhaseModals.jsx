import { useState } from 'react'
import { useLang } from '../../i18n'

function ModalShell({ children }) {
  return (
    <div className="ui-modal-mask fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="ui-card ui-modal w-full max-w-md p-5">{children}</div>
    </div>
  )
}

// 进入弹窗：开会话即判定灵感已构成观点，询问是否直接生成分析进入打磨
export function PolishEntryModal({ busy, error, onConfirm, onStay }) {
  const { t } = useLang()
  return (
    <ModalShell>
      <h3 className="text-sm font-bold text-ink">{t('polishEntryTitle')}</h3>
      <p className="mt-2 text-sm text-ink-2">{t('polishEntryBody')}</p>
      <p className="mt-1 text-xs text-ink-3">{t('polishTitleNote')}</p>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <button
          className="ui-btn-ghost px-3 py-1.5 text-sm"
          onClick={onStay}
          disabled={busy}
        >
          {t('polishEntryStay')}
        </button>
        <button
          className="ui-btn-primary px-3 py-1.5 text-sm disabled:opacity-50"
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? t('generating') : t('polishEntryConfirm')}
        </button>
      </div>
    </ModalShell>
  )
}

// 收敛弹窗：AI 判定讨论收敛（或手动进入打磨）时，确认草稿后生成分析进入打磨
export function PolishReadyModal({ busy, error, initialDraft, onConfirm, onStay }) {
  const { t } = useLang()
  const [draft, setDraft] = useState(initialDraft ?? '')
  const empty = !draft.trim()
  return (
    <ModalShell>
      <h3 className="text-sm font-bold text-ink">{t('polishReadyTitle')}</h3>
      <p className="mt-2 text-sm text-ink-2">{t('polishReadyBody')}</p>
      <p className="mt-1 text-xs text-ink-3">{t('polishTitleNote')}</p>
      <label className="mt-3 block text-xs text-ink-2">
        {t('polishDraftLabel')}
        <textarea
          className="ui-input mt-1 w-full p-2 text-sm text-ink"
          rows={5}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={busy}
        />
      </label>
      {empty && <p className="mt-1 text-xs text-danger">{t('draftRequired')}</p>}
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <div className="mt-4 flex justify-end gap-2">
        <button
          className="ui-btn-ghost px-3 py-1.5 text-sm"
          onClick={onStay}
          disabled={busy}
        >
          {t('polishReadyStay')}
        </button>
        <button
          className="ui-btn-primary px-3 py-1.5 text-sm disabled:opacity-50"
          onClick={() => onConfirm(draft.trim())}
          disabled={busy || empty}
        >
          {busy ? t('generating') : t('polishEntryConfirm')}
        </button>
      </div>
    </ModalShell>
  )
}
