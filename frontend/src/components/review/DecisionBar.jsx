import { useEffect, useState } from 'react'
import {
  CIRCLE_OPTIONS,
  DISCIPLINE_OPTIONS,
  DOMAIN_OPTIONS,
  LAYER_OPTIONS,
  RELATION_LABELS,
  SCENE_OPTIONS,
  summarize,
} from '../../vocab'

function TagSelect({ label, options, value, onChange }) {
  return (
    <label className="block text-xs text-slate-500">
      {label}
      <select
        className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm text-slate-800"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">（留空）</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  )
}

export default function DecisionBar({ session, analysis, related, onSubmit }) {
  const [mode, setMode] = useState(null) // null | 'reject' | 'accept'
  const [reason, setReason] = useState('')
  const [finalContent, setFinalContent] = useState('')
  const [layer, setLayer] = useState('')
  const [tags, setTags] = useState({ domain: '', circle: '', discipline: '', scene: '' })
  const [selectedRelations, setSelectedRelations] = useState(new Set())
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setMode(null)
    setReason('')
    setError(null)
    setFinalContent(session?.inspiration?.content ?? '')
    setLayer(analysis?.layer ?? '')
    setTags({
      domain: analysis?.tags?.domain ?? '',
      circle: analysis?.tags?.circle ?? '',
      discipline: analysis?.tags?.discipline ?? '',
      scene: analysis?.tags?.scene ?? '',
    })
    setSelectedRelations(
      new Set((analysis?.relations ?? []).map((r) => r.viewpoint_id)),
    )
  }, [session, analysis])

  const disabled = !session || submitting

  function toggleRelation(viewpointId) {
    setSelectedRelations((prev) => {
      const next = new Set(prev)
      if (next.has(viewpointId)) next.delete(viewpointId)
      else next.add(viewpointId)
      return next
    })
  }

  async function submit(decisionType) {
    setError(null)
    if (decisionType === 'reject' && !reason.trim()) {
      setError('请填写否定理由')
      return
    }
    if (
      (decisionType === 'accept' || decisionType === 'accept_modified') &&
      !finalContent.trim()
    ) {
      setError('最终正文不能为空')
      return
    }
    const payload = { decision_type: decisionType }
    if (decisionType === 'reject') {
      payload.reason = reason.trim()
    }
    if (decisionType === 'accept' || decisionType === 'accept_modified') {
      payload.final_content = finalContent.trim()
      if (layer) payload.layer = layer
      payload.tags = {
        domain: tags.domain || null,
        circle: tags.circle || null,
        discipline: tags.discipline || null,
        scene: tags.scene || null,
      }
      payload.relations = (analysis?.relations ?? [])
        .filter((r) => selectedRelations.has(r.viewpoint_id))
        .map((r) => ({ viewpoint_id: r.viewpoint_id, type: r.type }))
    }
    setSubmitting(true)
    try {
      await onSubmit(payload)
      setMode(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function handleDefer() {
    if (!window.confirm('确认暂缓审议该灵感？它将回到待审队列。')) return
    submit('defer')
  }

  return (
    <>
      {mode === 'reject' && (
        <div className="fixed inset-x-0 bottom-16 z-10 flex justify-center px-4">
          <div className="w-full max-w-xl rounded-lg border border-slate-200 bg-white p-4 shadow-lg">
            <h3 className="text-sm font-bold text-slate-800">否定该灵感</h3>
            <textarea
              className="mt-2 w-full rounded border border-slate-300 p-2 text-sm outline-none focus:border-slate-500"
              rows={3}
              placeholder="请填写否定理由（必填）"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
            <div className="mt-3 flex justify-end gap-2">
              <button
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                onClick={() => setMode(null)}
                disabled={submitting}
              >
                取消
              </button>
              <button
                className="rounded bg-red-600 px-3 py-1.5 text-sm text-white hover:bg-red-500 disabled:opacity-50"
                onClick={() => submit('reject')}
                disabled={submitting}
              >
                {submitting ? '提交中…' : '确认否定'}
              </button>
            </div>
          </div>
        </div>
      )}

      {mode === 'accept' || mode === 'accept_modified' ? (
        <div className="fixed bottom-16 right-4 z-10 w-[min(42rem,92vw)]">
          <div className="max-h-[70vh] overflow-y-auto rounded-lg border border-slate-200 bg-white p-4 shadow-lg">
            <h3 className="text-sm font-bold text-slate-800">
              {mode === 'accept' ? '采纳为观点' : '修改后采纳'}
            </h3>
            <label className="mt-3 block text-xs text-slate-500">
              最终正文
              <textarea
                className="mt-1 w-full rounded border border-slate-300 p-2 text-sm text-slate-800 outline-none focus:border-slate-500"
                rows={5}
                value={finalContent}
                onChange={(e) => setFinalContent(e.target.value)}
              />
            </label>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
              <TagSelect
                label="分层"
                options={LAYER_OPTIONS}
                value={layer}
                onChange={setLayer}
              />
              <TagSelect
                label="领域"
                options={DOMAIN_OPTIONS}
                value={tags.domain}
                onChange={(v) => setTags((t) => ({ ...t, domain: v }))}
              />
              <TagSelect
                label="圈层"
                options={CIRCLE_OPTIONS}
                value={tags.circle}
                onChange={(v) => setTags((t) => ({ ...t, circle: v }))}
              />
              <TagSelect
                label="学科"
                options={DISCIPLINE_OPTIONS}
                value={tags.discipline}
                onChange={(v) => setTags((t) => ({ ...t, discipline: v }))}
              />
              <TagSelect
                label="场景"
                options={SCENE_OPTIONS}
                value={tags.scene}
                onChange={(v) => setTags((t) => ({ ...t, scene: v }))}
              />
            </div>

            {(analysis?.relations ?? []).length > 0 && (
              <div className="mt-3">
                <p className="text-xs text-slate-500">关联关系（勾选后随观点入库）</p>
                <ul className="mt-1 space-y-1">
                  {analysis.relations.map((rel) => {
                    const vp = related.find(
                      (r) => r.relation.viewpoint_id === rel.viewpoint_id,
                    )?.viewpoint
                    return (
                      <li key={`${rel.type}-${rel.viewpoint_id}`}>
                        <label className="flex items-center gap-2 text-sm text-slate-800">
                          <input
                            type="checkbox"
                            checked={selectedRelations.has(rel.viewpoint_id)}
                            onChange={() => toggleRelation(rel.viewpoint_id)}
                          />
                          <span
                            className={`rounded px-1.5 py-0.5 text-xs ${
                              rel.type === 'conflict'
                                ? 'bg-red-100 text-red-700'
                                : 'bg-slate-200 text-slate-600'
                            }`}
                          >
                            {RELATION_LABELS[rel.type] ?? rel.type}
                          </span>
                          <span className="min-w-0 truncate">
                            #{rel.viewpoint_id}{' '}
                            {vp ? summarize(vp.content, 40) : ''}
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}

            {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                onClick={() => setMode(null)}
                disabled={submitting}
              >
                取消
              </button>
              <button
                className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                onClick={() => submit(mode)}
                disabled={submitting}
              >
                {submitting
                  ? '提交中…'
                  : mode === 'accept'
                    ? '确认采纳'
                    : '确认修改后采纳'}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      <div className="fixed inset-x-0 bottom-0 z-10 border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <span className="text-sm text-slate-500">
            {session ? `正在审议灵感 #${session.inspiration_id}` : '未选择灵感'}
          </span>
          <div className="ml-auto flex gap-2">
            <button
              className="rounded border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50"
              onClick={() => setMode(mode === 'reject' ? null : 'reject')}
              disabled={disabled}
            >
              否定
            </button>
            <button
              className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              onClick={handleDefer}
              disabled={disabled}
            >
              暂缓
            </button>
            <button
              className="rounded bg-slate-800 px-4 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => setMode(mode === 'accept' ? null : 'accept')}
              disabled={disabled}
            >
              采纳
            </button>
            <button
              className="rounded bg-slate-600 px-4 py-2 text-sm text-white hover:bg-slate-500 disabled:opacity-50"
              onClick={() =>
                setMode(mode === 'accept_modified' ? null : 'accept_modified')
              }
              disabled={disabled}
            >
              修改后采纳
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
