import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import TranslatedText from '../TranslatedText'
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

function ReadOnlyPane({ label, children }) {
  return (
    <div>
      <span className="text-xs text-ink-2">{label}</span>
      <div className="mt-1 h-56 overflow-y-auto whitespace-pre-wrap rounded-input border border-rule bg-paper-2 p-2 text-sm text-ink">
        {children}
      </div>
    </div>
  )
}

/**
 * 打磨完成确认弹窗：AI 判定双方已就最终表述形成共识（ready_to_adopt）时弹出。
 * 三栏对照：左原灵感（只读）/ 中提炼观点（只读，进入打磨时暂存的快照）/
 * 右打磨观点（可编辑，预填 AI 给出的最终正文）。标题/分层/标签/关联随确认入库。
 */
export default function AdoptConfirmModal({
  session,
  analysis,
  related,
  initialDraft,
  onConfirm,
  onStay,
}) {
  const { t, lang } = useLang()
  const [finalContent, setFinalContent] = useState(initialDraft ?? '')
  const [titleZh, setTitleZh] = useState('')
  const [titleEn, setTitleEn] = useState('')
  const [titleLoading, setTitleLoading] = useState(false)
  const [layer, setLayer] = useState(analysis?.layer ?? '')
  const [tags, setTags] = useState({
    domain: analysis?.tags?.domain ?? '',
    circle: analysis?.tags?.circle ?? '',
    discipline: analysis?.tags?.discipline ?? '',
    scene: analysis?.tags?.scene ?? '',
  })
  const [selectedRelations, setSelectedRelations] = useState(
    new Set((analysis?.relations ?? []).map((r) => r.viewpoint_id)),
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  // 用户改过标题后不再用 AI 建议覆盖
  const titleTouchedRef = useRef(false)

  // 打开即按最终正文请 AI 给双语标题（失败留空由用户手填）
  useEffect(() => {
    const content = (initialDraft ?? '').trim()
    if (!content) return undefined
    let cancelled = false
    setTitleLoading(true)
    api
      .suggestTitle(content)
      .then((res) => {
        if (cancelled || titleTouchedRef.current) return
        setTitleZh(res?.title_zh ?? '')
        setTitleEn(res?.title_en ?? '')
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setTitleLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function toggleRelation(viewpointId) {
    setSelectedRelations((prev) => {
      const next = new Set(prev)
      if (next.has(viewpointId)) next.delete(viewpointId)
      else next.add(viewpointId)
      return next
    })
  }

  async function submit() {
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
      await onConfirm(payload)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const original = session?.source_inspiration ?? null

  return (
    <div className="ui-modal-mask fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="ui-card ui-modal max-h-[92vh] w-full max-w-5xl overflow-y-auto p-5">
        <h3 className="text-sm font-bold text-ink">{t('adoptReadyTitle')}</h3>
        <p className="mt-2 text-sm text-ink-2">{t('adoptReadyBody')}</p>

        <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
          <ReadOnlyPane label={t('originalPane')}>
            {original && (
              <TranslatedText
                contentZh={original.content_zh}
                contentEn={original.content_en}
                originalLang={original.original_lang}
              />
            )}
          </ReadOnlyPane>
          <ReadOnlyPane label={t('distilledPane')}>
            {session?.distilled_snapshot ?? t('noDistillSnapshot')}
          </ReadOnlyPane>
          <label className="block">
            <span className="text-xs text-ink-2">{t('polishedPane')}</span>
            <textarea
              className="ui-input mt-1 h-56 w-full resize-none p-2 text-sm text-ink"
              value={finalContent}
              onChange={(e) => setFinalContent(e.target.value)}
              disabled={submitting}
            />
          </label>
        </div>

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
            onChange={(v) => setTags((prev) => ({ ...prev, domain: v }))}
          />
          <TagSelect
            label={t('circle')}
            options={CIRCLE_OPTIONS}
            value={tags.circle}
            onChange={(v) => setTags((prev) => ({ ...prev, circle: v }))}
          />
          <TagSelect
            label={t('discipline')}
            options={DISCIPLINE_OPTIONS}
            value={tags.discipline}
            onChange={(v) => setTags((prev) => ({ ...prev, discipline: v }))}
          />
          <TagSelect
            label={t('scene')}
            options={SCENE_OPTIONS}
            value={tags.scene}
            onChange={(v) => setTags((prev) => ({ ...prev, scene: v }))}
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
            onClick={onStay}
            disabled={submitting}
          >
            {t('adoptReadyStay')}
          </button>
          <button
            className="ui-btn-gold px-3 py-1.5 text-sm"
            onClick={submit}
            disabled={submitting}
          >
            {submitting ? t('submitting') : t('adoptReadyConfirm')}
          </button>
        </div>
      </div>
    </div>
  )
}
