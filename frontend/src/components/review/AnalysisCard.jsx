import { useLang } from '../../i18n'
import { relationLabel, tagLabel } from '../../vocab'

function Section({ title, children }) {
  return (
    <section>
      <h3 className="text-xs font-bold text-ink-2">{title}</h3>
      <div className="mt-1 text-sm text-ink">{children}</div>
    </section>
  )
}

export default function AnalysisCard({ analysis, loading, onAnalyze }) {
  const { t, tf, lang } = useLang()
  const tags = analysis?.tags ?? {}

  return (
    <div className="ui-card p-4">
      <div className="flex items-center">
        <h2 className="text-sm font-bold text-ink">{t('aiAnalysis')}</h2>
        <button
          className="ui-btn-primary ml-auto px-3 py-1.5 text-sm"
          onClick={onAnalyze}
          disabled={loading}
        >
          {loading ? t('generating') : analysis ? t('regenerate') : t('generate')}
        </button>
      </div>

      {loading && <p className="mt-3 text-sm text-ink-3">{t('analyzing')}</p>}
      {!analysis && !loading && (
        <p className="mt-3 text-sm text-ink-3">{t('analysisHint')}</p>
      )}

      {analysis && (
        <div className="mt-3 space-y-4">
          <Section title={t('adoptionReason')}>
            <p className="whitespace-pre-wrap">{analysis.adoption_reason}</p>
          </Section>
          <Section title={t('strongestCounter')}>
            <p className="whitespace-pre-wrap">{analysis.strongest_counterargument}</p>
          </Section>
          <Section title={t('layerSuggestion')}>
            <p>{analysis.layer ? tagLabel(analysis.layer, lang) : t('none')}</p>
          </Section>
          <Section title={t('tagSuggestion')}>
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1">
              <li>
                {tf('domainLine', {
                  v: tags.domain ? tagLabel(tags.domain, lang) : t('none'),
                })}
              </li>
              <li>
                {tf('circleLine', {
                  v: tags.circle ? tagLabel(tags.circle, lang) : t('none'),
                })}
              </li>
              <li>
                {tf('disciplineLine', {
                  v: tags.discipline ? tagLabel(tags.discipline, lang) : t('none'),
                })}
              </li>
              <li>
                {tf('sceneLine', {
                  v: tags.scene ? tagLabel(tags.scene, lang) : t('none'),
                })}
              </li>
            </ul>
          </Section>
          <Section title={t('relationSuggestion')}>
            {analysis.relations?.length ? (
              <ul className="space-y-1">
                {analysis.relations.map((rel) => (
                  <li key={`${rel.type}-${rel.viewpoint_id}`}>
                    <span
                      className={`mr-1 rounded-pill px-1.5 py-0.5 text-xs ${
                        rel.type === 'conflict'
                          ? 'bg-danger-soft text-danger'
                          : 'bg-paper-2 text-ink-2'
                      }`}
                    >
                      {relationLabel(rel.type, lang)}
                    </span>
                    {tf('viewpointN', { id: rel.viewpoint_id })}
                  </li>
                ))}
              </ul>
            ) : (
              <p>{t('none')}</p>
            )}
          </Section>
        </div>
      )}
    </div>
  )
}
