import { useLang } from '../../i18n'
import TranslatedText from '../TranslatedText'
import {
  layerLabel,
  relationLabel,
  statusLabel,
  tagLabel,
} from '../../vocab'
import LlmSettingsCard from './LlmSettingsCard'

export default function RelationsPanel({ analysis, related }) {
  const { t, tf, lang } = useLang()
  const tags = analysis?.tags ?? {}

  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-white p-4 shadow">
        <h2 className="text-sm font-bold text-slate-800">{t('relatedViewpoints')}</h2>
        {!analysis ? (
          <p className="mt-2 text-sm text-slate-400">{t('relatedHintEmpty')}</p>
        ) : related.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">{t('noRelated')}</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {related.map(({ relation, viewpoint }) => (
              <li
                key={`${relation.type}-${relation.viewpoint_id}`}
                className="rounded border border-slate-200 p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs ${
                      relation.type === 'conflict'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-slate-200 text-slate-600'
                    }`}
                  >
                    {relationLabel(relation.type, lang)}
                  </span>
                  <span className="font-mono text-xs text-slate-400">
                    #{relation.viewpoint_id}
                  </span>
                </div>
                {viewpoint ? (
                  <>
                    <p className="mt-1 text-slate-800">
                      <TranslatedText
                        contentZh={viewpoint.content_zh ?? viewpoint.content}
                        contentEn={viewpoint.content_en ?? viewpoint.content}
                        originalLang={viewpoint.original_lang}
                        clamp
                      />
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {tf('layerLabel', {
                        v: layerLabel(viewpoint.layer, lang) ?? t('none'),
                      })}{' '}
                      · {tf('statusLabel', { v: statusLabel(viewpoint.status, lang) })}
                    </p>
                  </>
                ) : (
                  <p className="mt-1 text-xs text-red-500">{t('viewpointLoadFailed')}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-lg bg-white p-4 shadow">
        <h2 className="text-sm font-bold text-slate-800">{t('tagSuggestion')}</h2>
        {!analysis ? (
          <p className="mt-2 text-sm text-slate-400">{t('tagSuggestionHint')}</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-slate-800">
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
