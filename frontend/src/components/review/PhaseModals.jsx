import { useState } from 'react'
import TranslatedText from '../TranslatedText'
import { useLang } from '../../i18n'

function ModalShell({ children, wide = false }) {
  return (
    <div className="ui-modal-mask fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className={`ui-card ui-modal max-h-[90vh] w-full overflow-y-auto p-5 ${
          wide ? 'max-w-3xl' : 'max-w-md'
        }`}
      >
        {children}
      </div>
    </div>
  )
}

// 左栏原灵感（只读，随界面语言显示双语版本），右栏提炼观点（可编辑）
function DraftPanes({ original, draft, setDraft, busy, draftLabel }) {
  const { t } = useLang()
  return (
    <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div>
        <span className="text-xs text-ink-2">{t('originalPane')}</span>
        <div className="mt-1 h-56 overflow-y-auto whitespace-pre-wrap rounded-input border border-rule bg-paper-2 p-2 text-sm text-ink">
          {original && (
            <TranslatedText
              contentZh={original.content_zh}
              contentEn={original.content_en}
              originalLang={original.original_lang}
            />
          )}
        </div>
      </div>
      <label className="block">
        <span className="text-xs text-ink-2">{draftLabel}</span>
        <textarea
          className="ui-input mt-1 h-56 w-full resize-none p-2 text-sm text-ink"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={busy}
        />
      </label>
    </div>
  )
}

// 进入弹窗：开会话即判定灵感已构成观点，询问是否直接生成分析进入打磨。
// 跳过提炼时不存在提炼观点，不做正文对照，仅确认流程走向
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

// 收敛弹窗：AI 判定讨论收敛（或手动进入打磨）时，对照原灵感确认提炼观点后进入打磨
export function PolishReadyModal({ busy, error, original, initialDraft, onConfirm, onStay }) {
  const { t } = useLang()
  const [draft, setDraft] = useState(initialDraft ?? '')
  const empty = !draft.trim()
  return (
    <ModalShell wide>
      <h3 className="text-sm font-bold text-ink">{t('polishReadyTitle')}</h3>
      <p className="mt-2 text-sm text-ink-2">{t('polishReadyBody')}</p>
      <p className="mt-1 text-xs text-ink-3">{t('polishTitleNote')}</p>
      <DraftPanes
        original={original}
        draft={draft}
        setDraft={setDraft}
        busy={busy}
        draftLabel={t('distilledPane')}
      />
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
