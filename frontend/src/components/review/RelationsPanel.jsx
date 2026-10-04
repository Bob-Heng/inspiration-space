import { useLang } from '../../i18n'
import ItemTitle from '../ItemTitle'
import TranslatedText from '../TranslatedText'
import { layerLabel, relationLabel, tagLabel } from '../../vocab'
import LlmSettingsCard from './LlmSettingsCard'

export default function RelationsPanel({ analysis, related }) {
  const { t, tf, lang } = useLang()
  const tags = analysis?.tags ?? {}

  return (
    <div className="space-y-4">
      <div className="ui-card p-4">
        <h2 className="text-sm font-bold text-ink">{t('relatedViewpoints')}</h2>
        {!analysis ? (
          <p className="mt-2 text-sm text-ink-3">{t('relatedHintEmpty')}</p>
        ) : related.length === 0 ? (
          <p className="mt-2 text-sm text-ink-3">{t('noRelated')}</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {related.map(({ relation, viewpoint }) => (
              <li
                key={`${relation.type}-${relation.viewpoint_id}`}
                className="rounded border border-rule p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-pill px-1.5 py-0.5 text-xs ${
                      relation.type === 'conflict'
                        ? 'bg-danger-soft text-danger'
                        : 'bg-paper-2 text-ink-2'
                    }`}
                  >
                    {relationLabel(relation.type, lang)}
                  </span>
                  <span className="font-mono text-xs text-accent">
                    #{viewpoint?.source_inspiration_id ?? relation.viewpoint_id}
                  </span>
                </div>
                {viewpoint ? (
                  <>
                    <ItemTitle
                      titleZh={viewpoint.title_zh}
                      titleEn={viewpoint.title_en}
                      id={viewpoint.id}
                    />
                    <p className="mt-1 text-ink">
                      <TranslatedText
                        contentZh={viewpoint.content_zh}
                        contentEn={viewpoint.content_en}
                        originalLang={viewpoint.original_lang}
                        clamp
                      />
                    </p>
                    <p className="mt-1 text-xs text-ink-2">
                      {tf('layerLabel', {
                        v: layerLabel(viewpoint.layer, lang) ?? t('none'),
                      })}
                    </p>
                  </>
                ) : (
                  <p className="mt-1 text-xs text-danger">{t('viewpointLoadFailed')}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="ui-card p-4">
        <h2 className="text-sm font-bold text-ink">{t('tagSuggestion')}</h2>
        {!analysis ? (
          <p className="mt-2 text-sm text-ink-3">{t('tagSuggestionHint')}</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-ink">
            <li>
              {tf('layerLabel', {
                v: analysis.layer ? tagLabel(analysis.layer, lang) : t('none'),
              })}
            </li>
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
        )}
      </div>

      <LlmSettingsCard />
    </div>
  )
}
