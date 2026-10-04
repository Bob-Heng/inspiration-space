import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import ClassifiedView from '../components/viewpoints/ClassifiedView'
import SortToggle from '../components/SortToggle'
import ConflictMarks from '../components/viewpoints/ConflictMarks'
import ItemTitle from '../components/ItemTitle'
import ScrollElevator from '../components/ScrollElevator'
import TranslatedText from '../components/TranslatedText'
import ViewpointDetail from '../components/viewpoints/ViewpointDetail'
import { usePageHeader } from '../header'
import { LangSelect, useLang } from '../i18n'
import {
  CIRCLE_OPTIONS,
  DISCIPLINE_OPTIONS,
  DOMAIN_OPTIONS,
  LAYER_OPTIONS,
  SCENE_OPTIONS,
  formatDateTime,
  layerLabel,
  tagLabel,
  tagLine,
} from '../vocab'

const LAYER_CODES = { 道: 'dao', 法: 'fa', 术: 'shu' }

const EMPTY_FILTERS = {
  layer: '',
  domain: '',
  circle: '',
  discipline: '',
  scene: '',
  date_from: '',
  date_to: '',
  keyword: '',
}

const VIEW_TABS = [
  { key: 'table', labelKey: 'viewTable' },
  { key: 'cards', labelKey: 'viewCard' },
  { key: 'classified', labelKey: 'viewClassifiedTab' },
]

export default function ViewpointsPage() {
  const { t, tf, lang } = useLang()
  const [view, setView] = useState('table')
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [items, setItems] = useState([])
  const [sortOrder, setSortOrder] = useState('asc')
  const [error, setError] = useState(null)
  const [selectedId, setSelectedId] = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await api.listViewpoints(filters)
      setItems(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [filters])

  useEffect(() => {
    load()
  }, [load])

  function setFilter(key) {
  return (e) => setFilters((f) => ({ ...f, [key]: e.target.value }))
  }

// 开发模式（vite 5173）跨端口下载；打包后同源
const EXPORT_BASE = import.meta.env.DEV ? 'http://localhost:8000' : ''

  const headerItems = useMemo(
    () => [
      {
        hk: 'export-raw',
        node: (
          <a href={`${EXPORT_BASE}/api/export/viewpoints`} className="ui-link text-sm">
            {t('exportRaw')}
          </a>
        ),
      },
      {
        hk: 'export-classified',
        node: (
          <a href={`${EXPORT_BASE}/api/export/classified`} className="ui-link text-sm">
            {t('exportClassified')}
          </a>
        ),
      },
      { hk: 'lang', node: <LangSelect /> },
      // eslint-disable-next-line react-hooks/exhaustive-deps
    ],
    [t, EXPORT_BASE],
  )
  usePageHeader({
    current: 'viewpoints',
    subtitle: t('viewpointLibrary'),
    slogan: t('viewpointsSlogan'),
    items: headerItems,
  })

  const sortedItems = [...items].sort((a, b) => {
    const da = a.source_inspiration_id ?? a.id
    const db = b.source_inspiration_id ?? b.id
    return sortOrder === 'asc' ? da - db : db - da
  })

  return (
    <div className="min-h-screen bg-paper">
      <main className="mx-auto max-w-7xl px-4 py-6">
        {view !== 'classified' && (
          <div className="ui-card ui-reveal p-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <select
                className="ui-input px-2 py-1.5"
                value={filters.layer}
                onChange={setFilter('layer')}
              >
                <option value="">{t('allLayer')}</option>
                {LAYER_OPTIONS.map((label) => (
                  <option key={label} value={LAYER_CODES[label]}>
                    {tagLabel(label, lang)}
                  </option>
                ))}
              </select>
              <select
                className="ui-input px-2 py-1.5"
                value={filters.domain}
                onChange={setFilter('domain')}
              >
                <option value="">{t('allDomain')}</option>
                {DOMAIN_OPTIONS.map((v) => (
                  <option key={v}>{tagLabel(v, lang)}</option>
                ))}
              </select>
              <select
                className="ui-input px-2 py-1.5"
                value={filters.circle}
                onChange={setFilter('circle')}
              >
                <option value="">{t('allCircle')}</option>
                {CIRCLE_OPTIONS.map((v) => (
                  <option key={v}>{tagLabel(v, lang)}</option>
                ))}
              </select>
              <select
                className="ui-input px-2 py-1.5"
                value={filters.discipline}
                onChange={setFilter('discipline')}
              >
                <option value="">{t('allDiscipline')}</option>
                {DISCIPLINE_OPTIONS.map((v) => (
                  <option key={v}>{tagLabel(v, lang)}</option>
                ))}
              </select>
              <select
                className="ui-input px-2 py-1.5"
                value={filters.scene}
                onChange={setFilter('scene')}
              >
                <option value="">{t('allScene')}</option>
                {SCENE_OPTIONS.map((v) => (
                  <option key={v}>{tagLabel(v, lang)}</option>
                ))}
              </select>
              <label className="text-ink-2">
                {t('colSourceDate')}
                <input
                  type="date"
                  className="ui-input ml-1 px-2 py-1"
                  value={filters.date_from}
                  onChange={setFilter('date_from')}
                />
                <span className="mx-1">{t('dateRangeSep')}</span>
                <input
                  type="date"
                  className="ui-input px-2 py-1"
                  value={filters.date_to}
                  onChange={setFilter('date_to')}
                />
              </label>
              <input
                className="ui-input w-48 px-3 py-1.5"
                placeholder={t('searchKeyword')}
                value={filters.keyword}
                onChange={setFilter('keyword')}
              />
              <button
                className="ui-btn-ghost px-3 py-1.5"
                onClick={() => setFilters(EMPTY_FILTERS)}
              >
                {t('reset')}
              </button>
            </div>
          </div>
        )}

        <div className="mt-4 flex items-center gap-2">
          {VIEW_TABS.map((tab) => (
            <button
              key={tab.key}
              className={`px-3 py-1.5 text-sm ${
                view === tab.key ? 'ui-btn-primary' : 'ui-btn-ghost'
              }`}
              onClick={() => setView(tab.key)}
            >
              {t(tab.labelKey)}
            </button>
          ))}
          <SortToggle order={sortOrder} onChange={setSortOrder} />
          <span className="ml-auto text-sm text-ink-2">
            {view === 'classified' ? '' : tf('totalItems', { n: items.length })}
          </span>
        </div>

        {error && <p className="mt-4 text-sm text-danger">{error}</p>}

        {view === 'classified' ? (
          <ClassifiedView onSelect={setSelectedId} sortOrder={sortOrder} />
        ) : view === 'table' ? (
          <div className="ui-card mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-rule text-left text-xs text-ink-2">
                  <th className="px-3 py-2">{t('colId')}</th>
                  <th className="px-3 py-2">{t('colContent')}</th>
                  <th className="px-3 py-2">{t('colLayer')}</th>
                  <th className="px-3 py-2">{t('colTags')}</th>
                  <th className="px-3 py-2">{t('colSourceDate')}</th>
                  <th className="px-3 py-2">{t('colCreatedAt')}</th>
                  <th className="px-3 py-2">{t('colActions')}</th>
                </tr>
              </thead>
              <tbody>
                {sortedItems.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-rule align-top transition-colors duration-200 hover:bg-paper-2"
                  >
                    <td className="px-3 py-2 font-mono text-xs text-accent">
                      #{item.source_inspiration_id ?? item.id}
                      <ConflictMarks conflictWith={item.conflict_with} />
                    </td>
                    <td className="max-w-md px-3 py-2 text-ink">
                      <ItemTitle titleZh={item.title_zh} titleEn={item.title_en} id={item.id} />
                      <TranslatedText
                        contentZh={item.content_zh}
                        contentEn={item.content_en}
                        originalLang={item.original_lang}
                        clamp
                      />
                    </td>
                    <td className="px-3 py-2 font-medium text-ink">
                      {layerLabel(item.layer, lang) ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-ink-2">
                      {tagLine(item, lang) || '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-ink-2">
                      {item.source_date ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-ink-2">
                      {formatDateTime(item.created_at, lang)}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        className="ui-link text-sm"
                        onClick={() => setSelectedId(item.id)}
                      >
                        {t('detail')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {sortedItems.length === 0 && (
              <p className="p-6 text-center text-sm text-ink-3">
                {t('noMatch')}
              </p>
            )}
          </div>
        ) : (
          <ul className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {sortedItems.map((item) => (
              <li key={item.id} className="ui-card p-4">
                <div className="flex items-start gap-2 text-xs text-ink-2">
                  <span className="flex flex-col">
                    <span className="font-mono text-accent">#{item.source_inspiration_id ?? item.id}</span>
                    <ConflictMarks conflictWith={item.conflict_with} />
                  </span>
                  <span className="font-medium text-ink">{layerLabel(item.layer, lang) ?? t('unlayered')}</span>
                </div>
                <ItemTitle titleZh={item.title_zh} titleEn={item.title_en} id={item.id} />
                <p className="mt-2 text-ink">
                  <TranslatedText
                    contentZh={item.content_zh}
                    contentEn={item.content_en}
                    originalLang={item.original_lang}
                    clamp
                  />
                </p>
                <p className="mt-2 text-xs text-ink-2">
                  {tagLine(item, lang) || t('noTags')} ·{' '}
                  {tf('sourceDate', { date: item.source_date ?? '—' })}
                </p>
                <button
                  className="ui-link mt-2 text-sm"
                  onClick={() => setSelectedId(item.id)}
                >
                  {t('detail')}
                </button>
              </li>
            ))}
            {sortedItems.length === 0 && (
              <li className="ui-card p-6 text-center text-sm text-ink-3">
                {t('noMatch')}
              </li>
            )}
          </ul>
        )}
      </main>

      {selectedId !== null && (
        <ViewpointDetail
          viewpointId={selectedId}
          onClose={() => setSelectedId(null)}
          onChanged={load}
        />
      )}
          <ScrollElevator />
    </div>
  )
}
