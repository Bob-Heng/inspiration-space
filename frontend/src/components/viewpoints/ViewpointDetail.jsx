import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import ItemTitle from '../ItemTitle'
import TranslatedText from '../TranslatedText'
import { useLang } from '../../i18n'
import {
  RELATION_LABELS,
  eventLabel,
  formatDateTime,
  layerLabel,
  relationLabel,
  statusLabel,
  summarize,
  tagLine,
} from '../../vocab'

function autoMergeContent(survivor, absorbed) {
  if (survivor.includes(absorbed)) return survivor
  if (absorbed.includes(survivor)) return absorbed
  return `${survivor}\n${absorbed}`
}

function relationDetail(detail, tf, lang) {
  if (!detail) return null
  if (detail.conflict_with) return tf('relConflictWith', { id: detail.conflict_with })
  if (detail.merged_into) return tf('relMergedInto', { id: detail.merged_into })
  if (detail.absorbed_id) return tf('relAbsorbed', { id: detail.absorbed_id })
  if (detail.split_from) return tf('relSplitFrom', { id: detail.split_from })
  if (detail.new_viewpoint_ids)
    return tf('relSplitInto', {
      ids: detail.new_viewpoint_ids
        .map((id) => `#${id}`)
        .join(lang === 'en' ? ', ' : '、'),
    })
  return null
}

export default function ViewpointDetail({ viewpointId, onClose, onChanged }) {
  const { t, tf, lang } = useLang()
  const [viewpoint, setViewpoint] = useState(null)
  const [inspiration, setInspiration] = useState(null)
  const [relations, setRelations] = useState([])
  const [history, setHistory] = useState([])
  const [review, setReview] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [relationForm, setRelationForm] = useState({ targetId: '', type: 'similar' })
  const [mergeForm, setMergeForm] = useState({ targetId: '', reason: '', content: '' })
  const [splitForm, setSplitForm] = useState({ text: '', reason: '' })
  const [rejectForm, setRejectForm] = useState({ open: false, reason: '' })

  const load = useCallback(async () => {
    try {
      const [detail, relationList, eventList, reviewHistory] = await Promise.all([
        api.getViewpoint(viewpointId),
        api.listViewpointRelations(viewpointId),
        api.getViewpointHistory(viewpointId),
        api.getReviewHistory(viewpointId),
      ])
      setViewpoint(detail)
      setRelations(relationList)
      setHistory(eventList)
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
    if (
      relationForm.type === 'conflict' &&
      !window.confirm(tf('confirmConflict', { a: viewpointId, b: targetId }))
    ) {
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
    const extra =
      relation.relation_type === 'conflict' ? t('confirmUnlinkConflictExtra') : ''
    if (!window.confirm(tf('confirmUnlink', { id: relation.viewpoint.id, extra })))
      return
    run(
      () => api.deleteViewpointRelation(viewpointId, relation.id),
      t('noticeRelationRemoved'),
    )
  }

  function handleSuspend() {
    if (!window.confirm(t('confirmSuspend'))) return
    run(
      () => api.updateViewpointStatus(viewpointId, { to_status: 'suspended' }),
      statusLabel('suspended', lang),
    )
  }

  function handleRestore() {
    if (!window.confirm(t('confirmRestore'))) return
    run(
      () => api.updateViewpointStatus(viewpointId, { to_status: 'accepted' }),
      t('noticeRestored'),
    )
  }

  function handleReject(e) {
    e.preventDefault()
    if (!rejectForm.reason.trim()) return
    if (!window.confirm(t('confirmRejectVp'))) return
    run(
      () =>
        api.updateViewpointStatus(viewpointId, {
          to_status: 'rejected',
          reason: rejectForm.reason.trim(),
        }),
      statusLabel('rejected', lang),
    )
    setRejectForm({ open: false, reason: '' })
  }

  async function handlePrefillMerge() {
    const targetId = Number(mergeForm.targetId)
    if (!targetId || !viewpoint) return
    try {
      const other = await api.getViewpoint(targetId)
      setMergeForm((f) => ({
        ...f,
        content: autoMergeContent(viewpoint.content, other.content),
      }))
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  function handleMerge(e) {
    e.preventDefault()
    const targetId = Number(mergeForm.targetId)
    if (!targetId || !mergeForm.reason.trim()) return
    if (!window.confirm(tf('confirmMerge', { target: targetId, id: viewpointId })))
      return
    run(
      () =>
        api.mergeViewpoint(viewpointId, {
          absorbed_id: targetId,
          merged_content: mergeForm.content.trim() || null,
          reason: mergeForm.reason.trim(),
        }),
      tf('noticeMerged', { id: targetId }),
    )
    setMergeForm({ targetId: '', reason: '', content: '' })
  }

  const splitParts = splitForm.text
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean)

  function handleSplit(e) {
    e.preventDefault()
    if (splitParts.length < 2 || !splitForm.reason.trim()) return
    if (
      !window.confirm(tf('confirmSplit', { n: splitParts.length, id: viewpointId }))
    )
      return
    run(
      () =>
        api.splitViewpoint(viewpointId, {
          parts: splitParts,
          reason: splitForm.reason.trim(),
        }),
      tf('noticeSplit', { n: splitParts.length }),
    )
    setSplitForm({ text: '', reason: '' })
  }

  const editable = viewpoint && viewpoint.status !== 'rejected'

  return (
    <div className="fixed inset-0 z-10 overflow-y-auto bg-slate-900/30 p-4">
      <div className="mx-auto my-8 max-w-3xl rounded-lg bg-white p-6 shadow-xl">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-slate-400">
            #{viewpoint?.source_inspiration_id ?? viewpointId}
          </span>
          {viewpoint && (
            <>
              <span className="text-sm text-slate-500">
                {layerLabel(viewpoint.layer, lang) ?? t('unlayered')}
              </span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                {statusLabel(viewpoint.status, lang)}
              </span>
            </>
          )}
          <button
            className="ml-auto text-sm text-slate-500 hover:text-slate-800"
            onClick={onClose}
          >
            {t('close')}
          </button>
        </div>

        {notice && (
          <p className="mt-3 rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
            {notice}
          </p>
        )}
        {error && (
          <p className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
        {!viewpoint ? (
          <p className="mt-6 text-sm text-slate-400">{t('loading')}</p>
        ) : (
          <>
            <ItemTitle
              titleZh={viewpoint.title_zh}
              titleEn={viewpoint.title_en}
              id={viewpoint.id}
            />
            <p className="mt-4 whitespace-pre-wrap text-slate-800">
              <TranslatedText
                contentZh={viewpoint.content_zh}
                contentEn={viewpoint.content_en}
                originalLang={viewpoint.original_lang}
                className="whitespace-pre-wrap"
              />
            </p>
            <p className="mt-2 text-xs text-slate-500">
              {tf('tagsLine', { v: tagLine(viewpoint, lang) || t('none') })} ·{' '}
              {tf('sourceDate', { date: viewpoint.source_date ?? '—' })} ·{' '}
              {tf('createdLine', { v: formatDateTime(viewpoint.created_at, lang) })} ·{' '}
              {tf('updatedLine', { v: formatDateTime(viewpoint.updated_at, lang) })}
            </p>

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">{t('vpSourceInspiration')}</h3>
              {inspiration ? (
                <div className="mt-2 rounded border border-slate-200 p-3 text-sm">
                  <span className="font-mono text-xs text-slate-400">
                    #{inspiration.id}
                  </span>
                  <ItemTitle
                    titleZh={inspiration.title_zh}
                    titleEn={inspiration.title_en}
                    id={inspiration.id}
                  />
                  <p className="mt-1 whitespace-pre-wrap text-slate-600">
                    <TranslatedText
                      contentZh={inspiration.content_zh}
                      contentEn={inspiration.content_en}
                      originalLang={inspiration.original_lang}
                    />
                  </p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-400">
                  {viewpoint.source_inspiration_id
                    ? t('vpSourceLoadFailed')
                    : t('vpNoSource')}
                </p>
              )}
            </section>

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">{t('vpRelations')}</h3>
              {relations.length === 0 ? (
                <p className="mt-2 text-sm text-slate-400">{t('vpNoRelations')}</p>
              ) : (
                <ul className="mt-2 space-y-2">
                  {relations.map((relation) => (
                    <li
                      key={relation.id}
                      className="flex items-start gap-2 rounded border border-slate-200 p-3 text-sm"
                    >
                      <span
                        className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${
                          relation.relation_type === 'conflict'
                            ? 'bg-red-100 text-red-700'
                            : 'bg-slate-200 text-slate-600'
                        }`}
                      >
                        {relationLabel(relation.relation_type, lang)}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="font-mono text-xs text-slate-400">
                          #{relation.viewpoint.id}
                        </span>
                        <span className="ml-2 text-slate-800">
                          {summarize(relation.viewpoint.content, 50)}
                        </span>
                        <span className="ml-2 text-xs text-slate-500">
                          {statusLabel(relation.viewpoint.status, lang)}
                        </span>
                      </span>
                      {editable && (
                        <button
                          className="shrink-0 text-xs text-red-500 hover:text-red-700"
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
                    className="w-28 rounded border border-slate-300 px-2 py-1.5"
                    placeholder={t('vpTargetId')}
                    value={relationForm.targetId}
                    onChange={(e) =>
                      setRelationForm((f) => ({ ...f, targetId: e.target.value }))
                    }
                  />
                  <select
                    className="rounded border border-slate-300 px-2 py-1.5"
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
                    className="rounded bg-slate-800 px-3 py-1.5 text-white hover:bg-slate-700"
                  >
                    {t('vpAddRelation')}
                  </button>
                </form>
              )}
            </section>

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">{t('vpStatusOps')}</h3>
              {!editable ? (
                <p className="mt-2 text-sm text-slate-400">
                  {t('vpRejectedFinal')}
                </p>
              ) : (
                <div className="mt-2 flex items-center gap-2 text-sm">
                  {viewpoint.status === 'accepted' && (
                    <button
                      className="rounded border border-amber-300 px-3 py-1.5 text-amber-700 hover:bg-amber-50"
                      onClick={handleSuspend}
                    >
                      {t('vpSuspend')}
                    </button>
                  )}
                  {viewpoint.status === 'suspended' && (
                    <button
                      className="rounded border border-green-300 px-3 py-1.5 text-green-700 hover:bg-green-50"
                      onClick={handleRestore}
                    >
                      {t('vpRestore')}
                    </button>
                  )}
                  <button
                    className="rounded border border-red-300 px-3 py-1.5 text-red-600 hover:bg-red-50"
                    onClick={() => setRejectForm((f) => ({ ...f, open: !f.open }))}
                  >
                    {t('reject')}
                  </button>
                </div>
              )}
              {rejectForm.open && editable && (
                <form onSubmit={handleReject} className="mt-2 space-y-2">
                  <textarea
                    className="w-full rounded border border-slate-300 p-2 text-sm outline-none focus:border-slate-500"
                    rows={2}
                    placeholder={t('vpRejectReasonPlaceholder')}
                    value={rejectForm.reason}
                    onChange={(e) =>
                      setRejectForm((f) => ({ ...f, reason: e.target.value }))
                    }
                  />
                  <button
                    type="submit"
                    className="rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-500"
                  >
                    {t('confirmReject')}
                  </button>
                </form>
              )}
            </section>

            {editable && (
              <section className="mt-6 border-t border-slate-100 pt-4">
                <h3 className="text-sm font-bold text-slate-800">{t('vpMerge')}</h3>
                <form onSubmit={handleMerge} className="mt-2 space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <input
                      className="w-28 rounded border border-slate-300 px-2 py-1.5"
                      placeholder={t('vpMergeTarget')}
                      value={mergeForm.targetId}
                      onChange={(e) =>
                        setMergeForm((f) => ({ ...f, targetId: e.target.value }))
                      }
                    />
                    <input
                      className="flex-1 rounded border border-slate-300 px-2 py-1.5"
                      placeholder={t('vpMergeReason')}
                      value={mergeForm.reason}
                      onChange={(e) =>
                        setMergeForm((f) => ({ ...f, reason: e.target.value }))
                      }
                    />
                    <button
                      type="button"
                      className="rounded border border-slate-300 px-3 py-1.5 text-slate-600 hover:text-slate-800"
                      onClick={handlePrefillMerge}
                    >
                      {t('vpMergePrefill')}
                    </button>
                  </div>
                  <textarea
                    className="w-full rounded border border-slate-300 p-2 outline-none focus:border-slate-500"
                    rows={4}
                    placeholder={t('vpMergeContentPlaceholder')}
                    value={mergeForm.content}
                    onChange={(e) =>
                      setMergeForm((f) => ({ ...f, content: e.target.value }))
                    }
                  />
                  <button
                    type="submit"
                    className="rounded bg-slate-800 px-3 py-1.5 text-white hover:bg-slate-700"
                  >
                    {t('vpMergeConfirm')}
                  </button>
                </form>
              </section>
            )}

            {editable && (
              <section className="mt-6 border-t border-slate-100 pt-4">
                <h3 className="text-sm font-bold text-slate-800">{t('vpSplit')}</h3>
                <form onSubmit={handleSplit} className="mt-2 space-y-2 text-sm">
                  <textarea
                    className="w-full rounded border border-slate-300 p-2 outline-none focus:border-slate-500"
                    rows={5}
                    placeholder={t('vpSplitPlaceholder')}
                    value={splitForm.text}
                    onChange={(e) =>
                      setSplitForm((f) => ({ ...f, text: e.target.value }))
                    }
                  />
                  <div className="flex items-center gap-2">
                    <input
                      className="flex-1 rounded border border-slate-300 px-2 py-1.5"
                      placeholder={t('vpSplitReason')}
                      value={splitForm.reason}
                      onChange={(e) =>
                        setSplitForm((f) => ({ ...f, reason: e.target.value }))
                      }
                    />
                    <span className="text-xs text-slate-500">
                      {tf('vpSplitCount', { n: splitParts.length })}
                    </span>
                    <button
                      type="submit"
                      className="rounded bg-slate-800 px-3 py-1.5 text-white hover:bg-slate-700 disabled:opacity-40"
                      disabled={splitParts.length < 2}
                    >
                      {t('vpSplitConfirm')}
                    </button>
                  </div>
                </form>
              </section>
            )}

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">{t('vpReviewHistory')}</h3>
              {!review ? (
                <p className="mt-2 text-sm text-slate-400">
                  {t('vpNoReview')}
                </p>
              ) : (
                <div className="mt-2 space-y-3">
                  {review.decision && (
                    <p className="rounded bg-slate-50 px-3 py-2 text-xs text-slate-500">
                      {t('decisionPrefix')}
                      {t('decisionTypes')[review.decision.decision_type] ??
                        review.decision.decision_type}
                      {review.decision.reason
                        ? ` · ${t('vpReasonPrefix')}${review.decision.reason}`
                        : ''}
                    </p>
                  )}
                  {review.messages.length === 0 ? (
                    <p className="text-sm text-slate-400">{t('vpReviewNoMessages')}</p>
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
                            className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                              msg.role === 'user'
                                ? 'bg-slate-800 text-white'
                                : 'bg-slate-100 text-slate-800'
                            }`}
                          >
                            <p
                              className={`mb-0.5 text-xs ${
                                msg.role === 'user'
                                  ? 'text-slate-300'
                                  : 'text-slate-400'
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

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">{t('vpHistory')}</h3>
              {history.length === 0 ? (
                <p className="mt-2 text-sm text-slate-400">{t('vpNoHistory')}</p>
              ) : (
                <ul className="mt-2 space-y-1 text-sm">
                  {history.map((event) => (
                    <li key={event.id} className="text-slate-600">
                      <span className="text-xs text-slate-400">
                        {formatDateTime(event.created_at, lang)}
                      </span>
                      <span className="ml-2">
                        {eventLabel(event.event_type, lang)}
                      </span>
                      {(event.from_status || event.to_status) && (
                        <span className="ml-2 text-xs text-slate-500">
                          {statusLabel(event.from_status, lang) ?? '—'} →{' '}
                          {statusLabel(event.to_status, lang) ?? '—'}
                        </span>
                      )}
                      {relationDetail(event.detail, tf, lang) && (
                        <span className="ml-2 text-xs text-slate-500">
                          {relationDetail(event.detail, tf, lang)}
                        </span>
                      )}
                      {event.reason && (
                        <span className="ml-2 text-xs text-slate-500">
                          {t('reasonPrefix')}
                          {event.reason}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
