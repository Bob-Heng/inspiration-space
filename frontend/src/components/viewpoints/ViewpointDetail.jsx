import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import ItemTitle from '../ItemTitle'
import TranslatedText from '../TranslatedText'
import { useLang } from '../../i18n'
import {
  RELATION_LABELS,
  formatDateTime,
  layerLabel,
  relationLabel,
  summarize,
  tagLine,
} from '../../vocab'

export default function ViewpointDetail({ viewpointId, onClose, onChanged }) {
  const { t, tf, lang } = useLang()
  const [viewpoint, setViewpoint] = useState(null)
  const [inspiration, setInspiration] = useState(null)
  const [relations, setRelations] = useState([])
  const [review, setReview] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [relationForm, setRelationForm] = useState({ targetId: '', type: 'similar' })
  const [titleEditing, setTitleEditing] = useState(false)
  const [titleForm, setTitleForm] = useState({ zh: '', en: '' })
  const [titleError, setTitleError] = useState(null)
  const [titleSaving, setTitleSaving] = useState(false)

  const load = useCallback(async () => {
    try {
      const [detail, relationList, reviewHistory] = await Promise.all([
        api.getViewpoint(viewpointId),
        api.listViewpointRelations(viewpointId),
        api.getReviewHistory(viewpointId),
      ])
      setViewpoint(detail)
      setRelations(relationList)
      setReview(reviewHistory?.exists ? reviewHistory : null)
      setError(null)
      if (detail.source_inspiration_id) {
        try {
          setInspiration(await api.getInspiration(detail.source_inspiration_id))
        } catch {
          setInspiration(null)
        }
      }
    } catch (err) {
      setError(err.message)
    }
  }, [viewpointId])

  useEffect(() => {
    load()
  }, [load])

  async function run(action, message) {
    try {
      await action()
      setNotice(message)
      setError(null)
      await load()
      onChanged()
    } catch (err) {
      setError(err.message)
      setNotice(null)
    }
  }

  function handleCreateRelation(e) {
    e.preventDefault()
    const targetId = Number(relationForm.targetId)
    if (!targetId) return
    if (relationForm.type === 'conflict' && !window.confirm(t('confirmConflict'))) {
      return
    }
    run(
      () =>
        api.createViewpointRelation(viewpointId, {
          to_viewpoint_id: targetId,
          relation_type: relationForm.type,
        }),
      relationForm.type === 'conflict'
        ? t('noticeConflictCreated')
        : t('noticeRelationCreated'),
    )
    setRelationForm({ targetId: '', type: 'similar' })
  }

  function handleDeleteRelation(relation) {
    if (!window.confirm(tf('confirmUnlink', { id: relation.viewpoint.source_inspiration_id ?? relation.viewpoint.id }))) return
    run(
      () => api.deleteViewpointRelation(viewpointId, relation.id),
      t('noticeRelationRemoved'),
    )
  }

  // 撤回：accepted → draft，回他山坊打磨队列（详情保留展示，操作区随之收起）
  function handleWithdraw() {
    if (!window.confirm(t('withdrawConfirm'))) return
    run(() => api.withdrawViewpoint(viewpointId), t('noticeWithdrawn'))
  }

  function openTitleEdit() {
    setTitleForm({
      zh: viewpoint?.title_zh ?? '',
      en: viewpoint?.title_en ?? '',
    })
    setTitleError(null)
    setTitleEditing(true)
  }

  async function handleTitleSave(e) {
    e.preventDefault()
    const zh = titleForm.zh.trim()
    const en = titleForm.en.trim()
    if (!zh || !en) {
      setTitleError(t('titleRequired'))
      return
    }
    setTitleSaving(true)
    setTitleError(null)
    try {
      await api.updateViewpointTitle(viewpointId, { title_zh: zh, title_en: en })
      setViewpoint((v) => (v ? { ...v, title_zh: zh, title_en: en } : v))
      setTitleEditing(false)
    } catch (err) {
      setTitleError(err.message)
    } finally {
      setTitleSaving(false)
    }
  }

  // 仅 accepted（集思录在库）可编辑关系/标题/撤回；撤回后变 draft 转为只读
  const editable = viewpoint && viewpoint.status === 'accepted'

  return (
    <div className="ui-modal-mask fixed inset-0 z-10 overflow-y-auto p-4">
      <div className="ui-card ui-modal mx-auto my-8 max-w-3xl p-6">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-accent">
            #{viewpoint?.source_inspiration_id ?? viewpointId}
          </span>
          {viewpoint && (
            <span className="text-sm text-ink-2">
              {layerLabel(viewpoint.layer, lang) ?? t('unlayered')}
            </span>
          )}
          <button
            className="ui-link ml-auto text-sm"
            onClick={onClose}
          >
            {t('close')}
          </button>
        </div>

        {notice && (
          <p className="mt-3 rounded-input bg-accent-soft px-3 py-2 text-sm text-accent">
            {notice}
          </p>
        )}
        {error && (
          <p className="mt-3 rounded-input bg-danger-soft px-3 py-2 text-sm text-danger">
            {error}
          </p>
        )}
        {!viewpoint ? (
          <p className="mt-6 text-sm text-ink-3">{t('loading')}</p>
        ) : (
          <>
            {titleEditing ? (
              <form onSubmit={handleTitleSave} className="mt-2 space-y-2">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label className="block text-xs text-ink-2">
                    {t('titleZhLabel')}
                    <input
                      className="ui-input mt-1 w-full px-2 py-1.5 text-sm text-ink"
                      value={titleForm.zh}
                      onChange={(e) =>
                        setTitleForm((f) => ({ ...f, zh: e.target.value }))
                      }
                      autoFocus
                    />
                  </label>
                  <label className="block text-xs text-ink-2">
                    {t('titleEnLabel')}
                    <input
                      className="ui-input mt-1 w-full px-2 py-1.5 text-sm text-ink"
                      value={titleForm.en}
                      onChange={(e) =>
                        setTitleForm((f) => ({ ...f, en: e.target.value }))
                      }
                    />
                  </label>
                </div>
                {titleError && <p className="text-sm text-danger">{titleError}</p>}
                <div className="flex gap-2">
                  <button
                    type="submit"
                    className="ui-btn-primary px-3 py-1 text-sm"
                    disabled={titleSaving}
                  >
                    {t('save')}
                  </button>
                  <button
                    type="button"
                    className="ui-btn-ghost px-3 py-1 text-sm"
                    disabled={titleSaving}
                    onClick={() => setTitleEditing(false)}
                  >
                    {t('cancel')}
                  </button>
                </div>
              </form>
            ) : (
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <ItemTitle
                    titleZh={viewpoint.title_zh}
                    titleEn={viewpoint.title_en}
                    id={viewpoint.id}
                  />
                </div>
                {editable && (
                  <button
                    className="ui-link shrink-0 text-sm"
                    onClick={openTitleEdit}
                  >
                    {t('vpEditTitle')}
                  </button>
                )}
              </div>
            )}
            <p className="mt-4 whitespace-pre-wrap text-ink">
              <TranslatedText
                contentZh={viewpoint.content_zh}
                contentEn={viewpoint.content_en}
                originalLang={viewpoint.original_lang}
                className="whitespace-pre-wrap"
              />
            </p>
            <p className="mt-2 text-xs text-ink-2">
              {tf('tagsLine', { v: tagLine(viewpoint, lang) || t('none') })} ·{' '}
              {tf('sourceDate', { date: viewpoint.source_date ?? '—' })} ·{' '}
              {tf('createdLine', { v: formatDateTime(viewpoint.created_at, lang) })} ·{' '}
              {tf('updatedLine', { v: formatDateTime(viewpoint.updated_at, lang) })}
            </p>

            <section className="mt-6 border-t border-rule pt-4">
              <h3 className="text-sm font-bold text-ink">{t('vpSourceInspiration')}</h3>
              {inspiration ? (
                <div className="mt-2 rounded-input border border-rule p-3 text-sm">
                  <span className="font-mono text-xs text-accent">
                    #{inspiration.id}
                  </span>
                  <ItemTitle
                    titleZh={inspiration.title_zh}
                    titleEn={inspiration.title_en}
                    id={inspiration.id}
                  />
                  <p className="mt-1 whitespace-pre-wrap text-ink-2">
                    <TranslatedText
                      contentZh={inspiration.content_zh}
                      contentEn={inspiration.content_en}
                      originalLang={inspiration.original_lang}
                    />
                  </p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-ink-3">
                  {viewpoint.source_inspiration_id
                    ? t('vpSourceLoadFailed')
                    : t('vpNoSource')}
                </p>
              )}
            </section>

            <section className="mt-6 border-t border-rule pt-4">
              <h3 className="text-sm font-bold text-ink">{t('vpRelations')}</h3>
              {relations.length === 0 ? (
                <p className="mt-2 text-sm text-ink-3">{t('vpNoRelations')}</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {relations.map((relation) => (
                    <li
                      key={relation.id}
                      className="flex items-start gap-2 rounded-input border border-rule p-3 text-sm"
                    >
                      <span
                        className={`shrink-0 rounded-pill px-2 py-0.5 text-xs ${
                          relation.relation_type === 'conflict'
                            ? 'bg-danger-soft text-danger'
                            : 'bg-paper-2 text-ink-2'
                        }`}
                      >
                        {relationLabel(relation.relation_type, lang)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="font-mono text-xs text-accent">
                          #{relation.viewpoint.source_inspiration_id ?? relation.viewpoint.id}
                        </span>
                        <span className="ml-2 text-ink">
                          {summarize(relation.viewpoint.content, 50)}
                        </span>
                      </span>
                      {editable && (
                        <button
                          className="ui-link-danger shrink-0 text-xs"
                          onClick={() => handleDeleteRelation(relation)}
                        >
                          {t('vpUnlink')}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              {editable && (
                <form onSubmit={handleCreateRelation} className="mt-3 flex items-center gap-2 text-sm">
                  <input
                    className="ui-input w-28 px-2 py-1.5"
                    placeholder={t('vpTargetId')}
                    value={relationForm.targetId}
                    onChange={(e) =>
                      setRelationForm((f) => ({ ...f, targetId: e.target.value }))
                    }
                  />
                  <select
                    className="ui-input px-2 py-1.5"
                    value={relationForm.type}
                    onChange={(e) =>
                      setRelationForm((f) => ({ ...f, type: e.target.value }))
                    }
                  >
                    {Object.keys(RELATION_LABELS).map((value) => (
                      <option key={value} value={value}>
                        {relationLabel(value, lang)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="submit"
                    className="ui-btn-primary px-3 py-1.5"
                  >
                    {t('vpAddRelation')}
                  </button>
                </form>
              )}
            </section>

            {editable && (
              <section className="mt-6 border-t border-rule pt-4">
                <h3 className="text-sm font-bold text-ink">{t('vpWithdrawTitle')}</h3>
                <p className="mt-1 text-xs text-ink-2">{t('vpWithdrawHint')}</p>
                <button
                  className="ui-btn-danger mt-2 px-3 py-1.5 text-sm"
                  onClick={handleWithdraw}
                >
                  {t('vpWithdraw')}
                </button>
              </section>
            )}

            <section className="mt-6 border-t border-rule pt-4">
              <h3 className="text-sm font-bold text-ink">{t('vpReviewHistory')}</h3>
              {!review ? (
                <p className="mt-2 text-sm text-ink-3">
                  {t('vpNoReview')}
                </p>
              ) : (
                <div className="mt-2 space-y-3">
                  {review.decision && (
                    <p className="rounded-input bg-paper-2 px-3 py-2 text-xs text-ink-2">
                      {t('decisionPrefix')}
                      {t('decisionTypes')[review.decision.decision_type] ??
                        review.decision.decision_type}
                      {review.decision.reason
                        ? ` · ${t('vpReasonPrefix')}${review.decision.reason}`
                        : ''}
                    </p>
                  )}
                  {review.messages.length === 0 ? (
                    <p className="text-sm text-ink-3">{t('vpReviewNoMessages')}</p>
                  ) : (
                    <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
                      {review.messages.map((msg) => (
                        <li
                          key={msg.id}
                          className={`flex ${
                            msg.role === 'user' ? 'justify-end' : 'justify-start'
                          }`}
                        >
                          <div
                            className={`max-w-[85%] rounded-input px-3 py-2 text-sm ${
                              msg.role === 'user'
                                ? 'bg-accent text-accent-ink'
                                : 'bg-paper-2 text-ink'
                            }`}
                          >
                            <p
                              className={`mb-0.5 text-xs ${
                                msg.role === 'user'
                                  ? 'text-accent-ink/70'
                                  : 'text-ink-3'
                              }`}
                            >
                              {msg.role === 'user' ? t('me') : t('ai')}
                            </p>
                            <p className="whitespace-pre-wrap">
                              <TranslatedText
                                contentZh={msg.content_zh}
                                contentEn={msg.content_en}
                                originalLang={msg.original_lang}
                              />
                            </p>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
