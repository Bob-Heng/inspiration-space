import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import {
  EVENT_TYPE_LABELS,
  LAYER_LABELS,
  RELATION_LABELS,
  VIEWPOINT_STATUS_LABELS,
  formatDateTime,
  summarize,
  tagLine,
} from '../../vocab'

function autoMergeContent(survivor, absorbed) {
  if (survivor.includes(absorbed)) return survivor
  if (absorbed.includes(survivor)) return absorbed
  return `${survivor}\n${absorbed}`
}

function relationDetail(detail) {
  if (!detail) return null
  if (detail.conflict_with) return `与 #${detail.conflict_with} 冲突`
  if (detail.merged_into) return `并入 #${detail.merged_into}`
  if (detail.absorbed_id) return `吸收 #${detail.absorbed_id}`
  if (detail.split_from) return `拆自 #${detail.split_from}`
  if (detail.new_viewpoint_ids)
    return `拆出 ${detail.new_viewpoint_ids.map((id) => `#${id}`).join('、')}`
  return null
}

export default function ViewpointDetail({ viewpointId, onClose, onChanged }) {
  const [viewpoint, setViewpoint] = useState(null)
  const [inspiration, setInspiration] = useState(null)
  const [relations, setRelations] = useState([])
  const [history, setHistory] = useState([])
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [relationForm, setRelationForm] = useState({ targetId: '', type: 'similar' })
  const [mergeForm, setMergeForm] = useState({ targetId: '', reason: '', content: '' })
  const [splitForm, setSplitForm] = useState({ text: '', reason: '' })
  const [rejectForm, setRejectForm] = useState({ open: false, reason: '' })

  const load = useCallback(async () => {
    try {
      const [detail, relationList, eventList] = await Promise.all([
        api.getViewpoint(viewpointId),
        api.listViewpointRelations(viewpointId),
        api.getViewpointHistory(viewpointId),
      ])
      setViewpoint(detail)
      setRelations(relationList)
      setHistory(eventList)
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
      !window.confirm(
        `建立冲突关系后，#${viewpointId} 与 #${targetId} 双方都将转为已悬置（解除冲突不会自动恢复，需手动操作状态）。确认建立？`,
      )
    ) {
      return
    }
    run(
      () =>
        api.createViewpointRelation(viewpointId, {
          to_viewpoint_id: targetId,
          relation_type: relationForm.type,
        }),
      relationForm.type === 'conflict' ? '已建立冲突关系，双方转为已悬置' : '已建立关系',
    )
    setRelationForm({ targetId: '', type: 'similar' })
  }

  function handleDeleteRelation(relation) {
    const extra =
      relation.relation_type === 'conflict'
        ? '解除冲突不会自动恢复双方的悬置状态，需手动操作。'
        : ''
    if (!window.confirm(`确认解除与 #${relation.viewpoint.id} 的关系？${extra}`)) return
    run(
      () => api.deleteViewpointRelation(viewpointId, relation.id),
      '已解除关系',
    )
  }

  function handleSuspend() {
    if (
      !window.confirm(
        '悬置后该观点在分类视图中带悬置标记，待证据充分后再恢复。确认悬置？',
      )
    )
      return
    run(() => api.updateViewpointStatus(viewpointId, { to_status: 'suspended' }), '已悬置')
  }

  function handleRestore() {
    if (!window.confirm('恢复后该观点回到已采纳状态。确认恢复？')) return
    run(() => api.updateViewpointStatus(viewpointId, { to_status: 'accepted' }), '已恢复采纳')
  }

  function handleReject(e) {
    e.preventDefault()
    if (!rejectForm.reason.trim()) return
    if (
      !window.confirm(
        '否定是终态，不可恢复；观点将保留留档但不再进入分类视图。确认否定？',
      )
    )
      return
    run(
      () =>
        api.updateViewpointStatus(viewpointId, {
          to_status: 'rejected',
          reason: rejectForm.reason.trim(),
        }),
      '已否定',
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
    if (
      !window.confirm(
        `将把 #${targetId} 合并进 #${viewpointId}：正文接续保留，#${targetId} 转为已否定并留档可追溯。确认合并？`,
      )
    )
      return
    run(
      () =>
        api.mergeViewpoint(viewpointId, {
          absorbed_id: targetId,
          merged_content: mergeForm.content.trim() || null,
          reason: mergeForm.reason.trim(),
        }),
      `已合并，#${targetId} 转为已否定`,
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
      !window.confirm(
        `将拆分为 ${splitParts.length} 条新观点（继承分层/标签/来源），#${viewpointId} 转为已否定并留档可追溯。确认拆分？`,
      )
    )
      return
    run(
      () =>
        api.splitViewpoint(viewpointId, {
          parts: splitParts,
          reason: splitForm.reason.trim(),
        }),
      `已拆分为 ${splitParts.length} 条新观点`,
    )
    setSplitForm({ text: '', reason: '' })
  }

  const editable = viewpoint && viewpoint.status !== 'rejected'

  return (
    <div className="fixed inset-0 z-10 overflow-y-auto bg-slate-900/30 p-4">
      <div className="mx-auto my-8 max-w-3xl rounded-lg bg-white p-6 shadow-xl">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-slate-400">#{viewpointId}</span>
          {viewpoint && (
            <>
              <span className="text-sm text-slate-500">
                {LAYER_LABELS[viewpoint.layer] ?? '未分层'}
              </span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                {VIEWPOINT_STATUS_LABELS[viewpoint.status] ?? viewpoint.status}
              </span>
            </>
          )}
          <button
            className="ml-auto text-sm text-slate-500 hover:text-slate-800"
            onClick={onClose}
          >
            关闭
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
          <p className="mt-6 text-sm text-slate-400">加载中…</p>
        ) : (
          <>
            <p className="mt-4 whitespace-pre-wrap text-slate-800">
              {viewpoint.content}
            </p>
            <p className="mt-2 text-xs text-slate-500">
              标签：{tagLine(viewpoint) || '无'} · 来源日期：
              {viewpoint.source_date ?? '—'} · 入库：
              {formatDateTime(viewpoint.created_at)} · 更新：
              {formatDateTime(viewpoint.updated_at)}
            </p>

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">来源灵感</h3>
              {inspiration ? (
                <div className="mt-2 rounded border border-slate-200 p-3 text-sm">
                  <span className="font-mono text-xs text-slate-400">
                    #{inspiration.id}
                  </span>
                  <p className="mt-1 whitespace-pre-wrap text-slate-600">
                    {inspiration.content}
                  </p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-400">
                  {viewpoint.source_inspiration_id ? '来源灵感加载失败' : '无来源灵感'}
                </p>
              )}
            </section>

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">相近 / 冲突 / 相关关系</h3>
              {relations.length === 0 ? (
                <p className="mt-2 text-sm text-slate-400">暂无关系。</p>
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
                        {RELATION_LABELS[relation.relation_type] ??
                          relation.relation_type}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="font-mono text-xs text-slate-400">
                          #{relation.viewpoint.id}
                        </span>
                        <span className="ml-2 text-slate-800">
                          {summarize(relation.viewpoint.content, 50)}
                        </span>
                        <span className="ml-2 text-xs text-slate-500">
                          {VIEWPOINT_STATUS_LABELS[relation.viewpoint.status] ??
                            relation.viewpoint.status}
                        </span>
                      </span>
                      {editable && (
                        <button
                          className="shrink-0 text-xs text-red-500 hover:text-red-700"
                          onClick={() => handleDeleteRelation(relation)}
                        >
                          解除
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
                    placeholder="对方编号"
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
                    {Object.entries(RELATION_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="submit"
                    className="rounded bg-slate-800 px-3 py-1.5 text-white hover:bg-slate-700"
                  >
                    建立关系
                  </button>
                </form>
              )}
            </section>

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">状态操作</h3>
              {!editable ? (
                <p className="mt-2 text-sm text-slate-400">
                  已否定为终态，不可再变更状态。
                </p>
              ) : (
                <div className="mt-2 flex items-center gap-2 text-sm">
                  {viewpoint.status === 'accepted' && (
                    <button
                      className="rounded border border-amber-300 px-3 py-1.5 text-amber-700 hover:bg-amber-50"
                      onClick={handleSuspend}
                    >
                      悬置
                    </button>
                  )}
                  {viewpoint.status === 'suspended' && (
                    <button
                      className="rounded border border-green-300 px-3 py-1.5 text-green-700 hover:bg-green-50"
                      onClick={handleRestore}
                    >
                      恢复采纳
                    </button>
                  )}
                  <button
                    className="rounded border border-red-300 px-3 py-1.5 text-red-600 hover:bg-red-50"
                    onClick={() => setRejectForm((f) => ({ ...f, open: !f.open }))}
                  >
                    否定
                  </button>
                </div>
              )}
              {rejectForm.open && editable && (
                <form onSubmit={handleReject} className="mt-2 space-y-2">
                  <textarea
                    className="w-full rounded border border-slate-300 p-2 text-sm outline-none focus:border-slate-500"
                    rows={2}
                    placeholder="否定理由（必填）"
                    value={rejectForm.reason}
                    onChange={(e) =>
                      setRejectForm((f) => ({ ...f, reason: e.target.value }))
                    }
                  />
                  <button
                    type="submit"
                    className="rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-500"
                  >
                    确认否定
                  </button>
                </form>
              )}
            </section>

            {editable && (
              <section className="mt-6 border-t border-slate-100 pt-4">
                <h3 className="text-sm font-bold text-slate-800">合并</h3>
                <form onSubmit={handleMerge} className="mt-2 space-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <input
                      className="w-28 rounded border border-slate-300 px-2 py-1.5"
                      placeholder="被合并方编号"
                      value={mergeForm.targetId}
                      onChange={(e) =>
                        setMergeForm((f) => ({ ...f, targetId: e.target.value }))
                      }
                    />
                    <input
                      className="flex-1 rounded border border-slate-300 px-2 py-1.5"
                      placeholder="合并原因（必填）"
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
                      预填接续正文
                    </button>
                  </div>
                  <textarea
                    className="w-full rounded border border-slate-300 p-2 outline-none focus:border-slate-500"
                    rows={4}
                    placeholder="合并后的正文（留空则自动无损接续双方正文，可预填后微调）"
                    value={mergeForm.content}
                    onChange={(e) =>
                      setMergeForm((f) => ({ ...f, content: e.target.value }))
                    }
                  />
                  <button
                    type="submit"
                    className="rounded bg-slate-800 px-3 py-1.5 text-white hover:bg-slate-700"
                  >
                    确认合并
                  </button>
                </form>
              </section>
            )}

            {editable && (
              <section className="mt-6 border-t border-slate-100 pt-4">
                <h3 className="text-sm font-bold text-slate-800">拆分</h3>
                <form onSubmit={handleSplit} className="mt-2 space-y-2 text-sm">
                  <textarea
                    className="w-full rounded border border-slate-300 p-2 outline-none focus:border-slate-500"
                    rows={5}
                    placeholder="每条新观点正文之间用空行分隔（至少 2 条）"
                    value={splitForm.text}
                    onChange={(e) =>
                      setSplitForm((f) => ({ ...f, text: e.target.value }))
                    }
                  />
                  <div className="flex items-center gap-2">
                    <input
                      className="flex-1 rounded border border-slate-300 px-2 py-1.5"
                      placeholder="拆分原因（必填）"
                      value={splitForm.reason}
                      onChange={(e) =>
                        setSplitForm((f) => ({ ...f, reason: e.target.value }))
                      }
                    />
                    <span className="text-xs text-slate-500">
                      将拆出 {splitParts.length} 条
                    </span>
                    <button
                      type="submit"
                      className="rounded bg-slate-800 px-3 py-1.5 text-white hover:bg-slate-700 disabled:opacity-40"
                      disabled={splitParts.length < 2}
                    >
                      确认拆分
                    </button>
                  </div>
                </form>
              </section>
            )}

            <section className="mt-6 border-t border-slate-100 pt-4">
              <h3 className="text-sm font-bold text-slate-800">操作留痕</h3>
              {history.length === 0 ? (
                <p className="mt-2 text-sm text-slate-400">暂无写操作记录。</p>
              ) : (
                <ul className="mt-2 space-y-1 text-sm">
                  {history.map((event) => (
                    <li key={event.id} className="text-slate-600">
                      <span className="text-xs text-slate-400">
                        {formatDateTime(event.created_at)}
                      </span>
                      <span className="ml-2">
                        {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
                      </span>
                      {(event.from_status || event.to_status) && (
                        <span className="ml-2 text-xs text-slate-500">
                          {VIEWPOINT_STATUS_LABELS[event.from_status] ?? '—'} →{' '}
                          {VIEWPOINT_STATUS_LABELS[event.to_status] ?? '—'}
                        </span>
                      )}
                      {relationDetail(event.detail) && (
                        <span className="ml-2 text-xs text-slate-500">
                          {relationDetail(event.detail)}
                        </span>
                      )}
                      {event.reason && (
                        <span className="ml-2 text-xs text-slate-500">
                          原因：{event.reason}
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
