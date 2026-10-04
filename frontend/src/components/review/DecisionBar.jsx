import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import { useLang } from '../../i18n'
import {
  CIRCLE_OPTIONS,
  DISCIPLINE_OPTIONS,
  DOMAIN_OPTIONS,
  LAYER_OPTIONS,
  SCENE_OPTIONS,
  relationLabel,
  summarize,
  tagLabel,
} from '../../vocab'

function TagSelect({ label, options, value, onChange }) {
  const { t, lang } = useLang()
  return (
    <label className="block text-xs text-ink-2">
      {label}
      <select
        className="ui-input mt-1 w-full px-2 py-1.5 text-sm text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{t('emptyOption')}</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {tagLabel(o, lang)}
          </option>
        ))}
      </select>
    </label>
  )
}

// 撤销键长按触发阶段级回退的时长
const LONG_PRESS_MS = 3000

export default function DecisionBar({
  phase: phaseProp,
  session,
  analysis,
  related,
  onSubmit,
  onUndo,
  onUndoPhase,
}) {
  const { t, tf, lang } = useLang()
  const [acceptOpen, setAcceptOpen] = useState(false)
  const [finalContent, setFinalContent] = useState('')
  const [titleZh, setTitleZh] = useState('')
  const [titleEn, setTitleEn] = useState('')
  const [titleLoading, setTitleLoading] = useState(false)
  const [layer, setLayer] = useState('')
  const [tags, setTags] = useState({ domain: '', circle: '', discipline: '', scene: '' })
  const [selectedRelations, setSelectedRelations] = useState(new Set())
  const [submitting, setSubmitting] = useState(false)
  const [undoBusy, setUndoBusy] = useState(false)
  const [error, setError] = useState(null)
  // 用户改过标题后不再用 AI 建议覆盖
  const titleTouchedRef = useRef(false)
  const pressTimerRef = useRef(null)
  const longPressFiredRef = useRef(false)

  // 阶段由父级传入（两阶段都渲染决策栏：distill 仅撤销，polish 撤销+采纳）
  const phase = phaseProp ?? session?.phase ?? 'polish'
  const active = session?.status === 'active'
  // 当前阶段消息数：消息带 phase 字段时按阶段过滤，不带则全部计入（由后端兜底拒空撤）
  const phaseMessageCount = (session?.messages ?? []).filter(
    (m) => !m.phase || m.phase === phase,
  ).length
  const undoDisabled = !session || !active || phaseMessageCount === 0 || undoBusy
  // 撤销地板：跳过提炼的观点（录入时已构成观点且无提炼消息），阶段回退无事可做，
  // 长按禁用（单击撤销本就限当前阶段，不受影响；后端 undo-phase 在此地板返回 409 兜底）
  const undoPhaseFloor =
    phase === 'polish' &&
    session?.viewpoint?.is_viewpoint === true &&
    !(session?.messages ?? []).some((m) => m.phase === 'distill')

  useEffect(
    () => () => {
      if (pressTimerRef.current) clearTimeout(pressTimerRef.current)
    },
    [],
  )

  function toggleRelation(viewpointId) {
    setSelectedRelations((prev) => {
      const next = new Set(prev)
      if (next.has(viewpointId)) next.delete(viewpointId)
      else next.add(viewpointId)
      return next
    })
  }

  // 打开采纳对话框：正文预填观点工作稿，分层/标签预填分析建议，并请 AI 给双语标题
  function openAccept() {
    setError(null)
    const content = session?.viewpoint?.content ?? ''
    setFinalContent(content)
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
    setTitleZh('')
    setTitleEn('')
    titleTouchedRef.current = false
    setAcceptOpen(true)
    if (content.trim()) {
      setTitleLoading(true)
      api
        .suggestTitle(content)
        .then((res) => {
          if (titleTouchedRef.current) return
          setTitleZh(res?.title_zh ?? '')
          setTitleEn(res?.title_en ?? '')
        })
        .catch(() => {
          // 标题生成失败静默：留空由用户手填
        })
        .finally(() => setTitleLoading(false))
    }
  }

  async function submitAccept() {
    setError(null)
    if (!finalContent.trim()) {
      setError(t('finalContentRequired'))
      return
    }
    if (!titleZh.trim() || !titleEn.trim()) {
      setError(t('titleRequired'))
      return
    }
    const payload = {
      decision_type: 'accept',
      final_content: finalContent.trim(),
      title_zh: titleZh.trim(),
      title_en: titleEn.trim(),
      tags: {
        domain: tags.domain || null,
        circle: tags.circle || null,
        discipline: tags.discipline || null,
        scene: tags.scene || null,
      },
      relations: (analysis?.relations ?? [])
        .filter((r) => selectedRelations.has(r.viewpoint_id))
        .map((r) => ({ viewpoint_id: r.viewpoint_id, type: r.type })),
    }
    if (layer) payload.layer = layer
    setSubmitting(true)
    try {
      await onSubmit(payload)
      setAcceptOpen(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  // 单击撤销：长按已触发过时抑制本次单击
  async function handleUndoClick() {
    if (longPressFiredRef.current) {
      longPressFiredRef.current = false
      return
    }
    if (undoDisabled) return
    setUndoBusy(true)
    try {
      await onUndo()
    } finally {
      setUndoBusy(false)
    }
  }

  // 长按 3 秒：阶段级回退（pointerup/leave 取消计时）；撤销地板上长按禁用
  function handlePressStart() {
    if (undoDisabled || undoPhaseFloor) return
    longPressFiredRef.current = false
    pressTimerRef.current = setTimeout(() => {
      pressTimerRef.current = null
      longPressFiredRef.current = true
      const key =
        phase === 'polish' ? 'undoPhasePolishConfirm' : 'undoPhaseDistillConfirm'
      if (!window.confirm(t(key))) return
      setUndoBusy(true)
      Promise.resolve(onUndoPhase()).finally(() => setUndoBusy(false))
    }, LONG_PRESS_MS)
  }

  function handlePressCancel() {
    if (pressTimerRef.current) {
      clearTimeout(pressTimerRef.current)
      pressTimerRef.current = null
    }
  }

  return (
    <>
      {acceptOpen && (
        <div className="fixed bottom-16 right-4 z-10 w-[min(42rem,92vw)]">
          <div className="ui-card max-h-[70vh] overflow-y-auto p-4">
            <h3 className="text-sm font-bold text-ink">{t('acceptTitle')}</h3>
            <label className="mt-3 block text-xs text-ink-2">
              {t('finalContent')}
              <textarea
                className="ui-input mt-1 w-full p-2 text-sm text-ink"
                rows={5}
                value={finalContent}
                onChange={(e) => setFinalContent(e.target.value)}
              />
            </label>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <label className="block text-xs text-ink-2">
                {t('titleZhLabel')}
                <input
                  className="ui-input mt-1 w-full px-2 py-1.5 text-sm text-ink"
                  value={titleZh}
                  placeholder={titleLoading ? t('titleGenerating') : ''}
                  onChange={(e) => {
                    titleTouchedRef.current = true
                    setTitleZh(e.target.value)
                  }}
                />
              </label>
              <label className="block text-xs text-ink-2">
                {t('titleEnLabel')}
                <input
                  className="ui-input mt-1 w-full px-2 py-1.5 text-sm text-ink"
                  value={titleEn}
                  placeholder={titleLoading ? t('titleGenerating') : ''}
                  onChange={(e) => {
                    titleTouchedRef.current = true
                    setTitleEn(e.target.value)
                  }}
                />
              </label>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
              <TagSelect
                label={t('layer')}
                options={LAYER_OPTIONS}
                value={layer}
                onChange={setLayer}
              />
              <TagSelect
                label={t('domain')}
                options={DOMAIN_OPTIONS}
                value={tags.domain}
                onChange={(v) => setTags((t) => ({ ...t, domain: v }))}
              />
              <TagSelect
                label={t('circle')}
                options={CIRCLE_OPTIONS}
                value={tags.circle}
                onChange={(v) => setTags((t) => ({ ...t, circle: v }))}
              />
              <TagSelect
                label={t('discipline')}
                options={DISCIPLINE_OPTIONS}
                value={tags.discipline}
                onChange={(v) => setTags((t) => ({ ...t, discipline: v }))}
              />
              <TagSelect
                label={t('scene')}
                options={SCENE_OPTIONS}
                value={tags.scene}
                onChange={(v) => setTags((t) => ({ ...t, scene: v }))}
              />
            </div>

            {(analysis?.relations ?? []).length > 0 && (
              <div className="mt-3">
                <p className="text-xs text-ink-2">{t('relationsToSave')}</p>
                <ul className="mt-1 space-y-1">
                  {analysis.relations.map((rel) => {
                    const vp = related.find(
                      (r) => r.relation.viewpoint_id === rel.viewpoint_id,
                    )?.viewpoint
                    return (
                      <li key={`${rel.type}-${rel.viewpoint_id}`}>
                        <label className="flex items-center gap-2 text-sm text-ink">
                          <input
                            type="checkbox"
                            checked={selectedRelations.has(rel.viewpoint_id)}
                            onChange={() => toggleRelation(rel.viewpoint_id)}
                          />
                          <span
                            className={`rounded-pill px-1.5 py-0.5 text-xs ${
                              rel.type === 'conflict'
                                ? 'bg-danger-soft text-danger'
                                : 'bg-paper-2 text-ink-2'
                            }`}
                          >
                            {relationLabel(rel.type, lang)}
                          </span>
                          <span className="min-w-0 truncate">
                            <span className="font-mono text-accent">
                              #{vp?.source_inspiration_id ?? rel.viewpoint_id}
                            </span>{' '}
                            {vp ? summarize(vp.content, 40) : ''}
                          </span>
                        </label>
                      </li>
                    )
                  })}
                </ul>
              </div>
            )}

            {error && <p className="mt-2 text-sm text-danger">{error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="ui-btn-ghost px-3 py-1.5 text-sm"
                onClick={() => setAcceptOpen(false)}
                disabled={submitting}
              >
                {t('cancel')}
              </button>
              <button
                className="ui-btn-gold px-3 py-1.5 text-sm"
                onClick={submitAccept}
                disabled={submitting}
              >
                {submitting ? t('submitting') : t('accept')}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="fixed inset-x-0 bottom-0 z-10 border-t border-rule bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
          <span className="text-sm text-ink-2">
            {session
              ? tf('reviewingN', { id: session.viewpoint?.source_inspiration_id ?? session.viewpoint_id })
              : t('noInspirationSelected')}
          </span>
          <div className="ml-auto flex gap-2">
            <button
              className={`ui-btn-danger px-4 py-2 text-sm${undoPhaseFloor ? ' opacity-60' : ''}`}
              title={undoPhaseFloor ? t('undoFloorHint') : undefined}
              onPointerDown={handlePressStart}
              onPointerUp={handlePressCancel}
              onPointerLeave={handlePressCancel}
              onClick={handleUndoClick}
              disabled={undoDisabled}
            >
              {t('undo')}
            </button>
            {phase === 'polish' && (
              <button
                className="ui-btn-gold px-4 py-2 text-sm"
                onClick={() => (acceptOpen ? setAcceptOpen(false) : openAccept())}
                disabled={!session || submitting}
              >
                {t('accept')}
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
