import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import ItemTitle from '../ItemTitle'
import ConflictMarks from './ConflictMarks'
import TranslatedText from '../TranslatedText'
import { useLang } from '../../i18n'
import { layerLabel, tagLine } from '../../vocab'

const GROUPS = ['dao', 'fa', 'shu']

export default function ClassifiedView({ onSelect, sortOrder = 'asc' }) {
  const { t, tf, lang } = useLang()
  const [groups, setGroups] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    try {
      setGroups(await api.getClassifiedViewpoints())
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (error) return <p className="mt-4 text-sm text-danger">{error}</p>
  if (!groups) return <p className="mt-4 text-sm text-ink-3">{t('loading')}</p>

  return (
    <div className="mt-4 space-y-4">
      <p className="text-xs text-ink-3">{t('classifiedNote')}</p>
      {GROUPS.map((layer) => (
        <section key={layer} className="ui-card p-4">
          <h2 className="border-b border-rule pb-2 font-display text-sm font-semibold text-ink">
            {layerLabel(layer, lang)}
            <span className="ml-2 text-xs font-normal text-ink-3">
              {tf('itemsCount', { n: groups[layer].length })}
            </span>
          </h2>
          {groups[layer].length === 0 ? (
            <p className="mt-2 text-sm text-ink-3">{t('groupEmpty')}</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {[...groups[layer]]
                .sort((a, b) => {
                  const da = a.source_inspiration_id ?? a.id
                  const db = b.source_inspiration_id ?? b.id
                  return sortOrder === 'asc' ? da - db : db - da
                })
                .map((item) => (
                <li
                  key={item.id}
                  className="rounded-input border border-rule p-3 text-sm"
                >
                  <div className="flex items-start gap-2 text-xs text-ink-2">
                    <span className="flex flex-col">
                      <span className="font-mono text-accent">#{item.source_inspiration_id ?? item.id}</span>
                      <ConflictMarks conflictWith={item.conflict_with} />
                    </span>
                    <span>{item.source_date ?? t('noSourceDateFull')}</span>
                    <button
                      className="ui-link ml-auto"
                      onClick={() => onSelect(item.id)}
                    >
                      {t('detail')}
                    </button>
                  </div>
                  <ItemTitle titleZh={item.title_zh} titleEn={item.title_en} id={item.id} />
                  <p className="mt-1 whitespace-pre-wrap text-ink">
                    <TranslatedText
                      contentZh={item.content_zh}
                      contentEn={item.content_en}
                      originalLang={item.original_lang}
                      clamp
                    />
                  </p>
                  {tagLine(item, lang) && (
                    <p className="mt-1 text-xs text-ink-2">{tagLine(item, lang)}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}
