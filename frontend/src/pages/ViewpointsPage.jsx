import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import ClassifiedView from '../components/viewpoints/ClassifiedView'
import PageHeader from '../components/PageHeader'
import TranslatedText from '../components/TranslatedText'
import ViewpointDetail from '../components/viewpoints/ViewpointDetail'
import { useLang } from '../i18n'
import {
  CIRCLE_OPTIONS,
  DISCIPLINE_OPTIONS,
  DOMAIN_OPTIONS,
  LAYER_OPTIONS,
  SCENE_OPTIONS,
  VIEWPOINT_STATUS_LABELS,
  formatDateTime,
  layerLabel,
  statusLabel,
  tagLabel,
  tagLine,
} from '../vocab'

const LAYER_CODES = { 道: 'dao', 法: 'fa', 术: 'shu' }

const STATUS_BADGES = {
  accepted: 'bg-green-100 text-green-700',
  suspended: 'bg-amber-100 text-amber-700',
  rejected: 'bg-slate-200 text-slate-500',
}

const EMPTY_FILTERS = {
  layer: '',
  status: '',
  domain: '',
  circle: '',
  discipline: '',
  scene: '',
  date_from: '',
  date_to: '',
  keyword: '',
}

export function StatusBadge({ status }) {
  const { lang } = useLang()
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-xs ${
        STATUS_BADGES[status] ?? 'bg-slate-200 text-slate-600'
      }`}
    >
      {statusLabel(status, lang)}
    </span>
  )
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

  return (
    <div className="min-h-screen bg-slate-50">      <PageHeader
        current="viewpoints"
        subtitle={t('viewpointLibrary')}
        extras={
          <>
            <a
              href={`${EXPORT_BASE}/api/export/viewpoints`}
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              {t('exportRaw')}
            </a>
            <a
              href={`${EXPORT_BASE}/api/export/classified`}
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              {t('exportClassified')}
            </a>
          </>
        }
      />

      <main className="mx-auto max-w-7xl px-4 py-6">
        {view !== 'classified' && (
          <div className="rounded-lg bg-white p-4 shadow">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
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
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.status}
              onChange={setFilter('status')}
            >
              <option value="">{t('allStatus')}</option>
              {Object.keys(VIEWPOINT_STATUS_LABELS).map((value) => (
                <option key={value} value={value}>
                  {statusLabel(value, lang)}
                </option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.domain}
              onChange={setFilter('domain')}
            >
              <option value="">{t('allDomain')}</option>
              {DOMAIN_OPTIONS.map((v) => (
                <option key={v}>{tagLabel(v, lang)}</option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.circle}
              onChange={setFilter('circle')}
            >
              <option value="">{t('allCircle')}</option>
              {CIRCLE_OPTIONS.map((v) => (
                <option key={v}>{tagLabel(v, lang)}</option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.discipline}
              onChange={setFilter('discipline')}
            >
              <option value="">{t('allDiscipline')}</option>
              {DISCIPLINE_OPTIONS.map((v) => (
                <option key={v}>{tagLabel(v, lang)}</option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.scene}
              onChange={setFilter('scene')}
            >
              <option value="">{t('allScene')}</option>
              {SCENE_OPTIONS.map((v) => (
                <option key={v}>{tagLabel(v, lang)}</option>
              ))}
            </select>
            <label className="text-slate-500">
              {t('colSourceDate')}
              <input
                type="date"
                className="ml-1 rounded border border-slate-300 px-2 py-1"
                value={filters.date_from}
                onChange={setFilter('date_from')}
              />
              <span className="mx-1">{t('dateRangeSep')}</span>
              <input
                type="date"
                className="rounded border border-slate-300 px-2 py-1"
                value={filters.date_to}
                onChange={setFilter('date_to')}
              />
            </label>
            <input
              className="w-48 rounded border border-slate-300 px-3 py-1.5 outline-none focus:border-slate-500"
              placeholder={t('searchKeyword')}
              value={filters.keyword}
              onChange={setFilter('keyword')}
            />
            <button
              className="rounded border border-slate-300 px-3 py-1.5 text-slate-500 hover:text-slate-800"
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
              className={`rounded px-3 py-1.5 text-sm ${
                view === tab.key
                  ? 'bg-slate-800 text-white'
                  : 'bg-white text-slate-600 shadow hover:text-slate-800'
              }`}
              onClick={() => setView(tab.key)}
            >
              {t(tab.labelKey)}
            </button>
          ))}
          <span className="ml-auto text-sm text-slate-500">
            {view === 'classified' ? '' : tf('totalItems', { n: items.length })}
          </span>
        </div>

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

        {view === 'classified' ? (
          <ClassifiedView onSelect={setSelectedId} />
        ) : view === 'table' ? (
          <div className="mt-4 overflow-x-auto rounded-lg bg-white shadow">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs text-slate-500">
                  <th className="px-3 py-2">{t('colId')}</th>
                  <th className="px-3 py-2">{t('colContent')}</th>
                  <th className="px-3 py-2">{t('colLayer')}</th>
                  <th className="px-3 py-2">{t('colTags')}</th>
                  <th className="px-3 py-2">{t('colStatus')}</th>
                  <th className="px-3 py-2">{t('colSourceDate')}</th>
                  <th className="px-3 py-2">{t('colCreatedAt')}</th>
                  <th className="px-3 py-2">{t('colActions')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className="border-b border-slate-100 align-top hover:bg-slate-50"
                  >
                    <td className="px-3 py-2 font-mono text-xs text-slate-400">
                      #{item.id}
                    </td>
                    <td className="max-w-md px-3 py-2 text-slate-800">
                      <TranslatedText
                        contentZh={item.content_zh ?? item.content}
                        contentEn={item.content_en ?? item.content}
                        originalLang={item.original_lang}
                        clamp
                      />
                    </td>
                    <td className="px-3 py-2">
                      {layerLabel(item.layer, lang) ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {tagLine(item, lang) || '—'}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {item.source_date ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {formatDateTime(item.created_at, lang)}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        className="text-sm text-slate-800 hover:underline"
                        onClick={() => setSelectedId(item.id)}
                      >
                        {t('detail')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {items.length === 0 && (
              <p className="p-6 text-center text-sm text-slate-400">
                {t('noMatch')}
              </p>
            )}
          </div>
        ) : (
          <ul className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <li key={item.id} className="rounded-lg bg-white p-4 shadow">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span className="font-mono text-slate-400">#{item.id}</span>
                  <span>{layerLabel(item.layer, lang) ?? t('unlayered')}</span>
                  <StatusBadge status={item.status} />
                </div>
                <p className="mt-2 text-slate-800">
                  <TranslatedText
                    contentZh={item.content_zh ?? item.content}
                    contentEn={item.content_en ?? item.content}
                    originalLang={item.original_lang}
                    clamp
                  />
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  {tagLine(item, lang) || t('noTags')} ·{' '}
                  {tf('sourceDate', { date: item.source_date ?? '—' })}
                </p>
                <button
                  className="mt-2 text-sm text-slate-800 hover:underline"
                  onClick={() => setSelectedId(item.id)}
                >
                  {t('detail')}
                </button>
              </li>
            ))}
            {items.length === 0 && (
              <li className="rounded-lg bg-white p-6 text-center text-sm text-slate-400 shadow">
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
    </div>
  )
}
