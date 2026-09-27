import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import ClassifiedView from '../components/viewpoints/ClassifiedView'
import ViewpointDetail from '../components/viewpoints/ViewpointDetail'
import {
  CIRCLE_OPTIONS,
  DISCIPLINE_OPTIONS,
  DOMAIN_OPTIONS,
  LAYER_LABELS,
  LAYER_OPTIONS,
  SCENE_OPTIONS,
  VIEWPOINT_STATUS_LABELS,
  formatDateTime,
  summarize,
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
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-xs ${
        STATUS_BADGES[status] ?? 'bg-slate-200 text-slate-600'
      }`}
    >
      {VIEWPOINT_STATUS_LABELS[status] ?? status}
    </span>
  )
}

const VIEW_TABS = [
  { key: 'table', label: '表格' },
  { key: 'cards', label: '卡片' },
  { key: 'classified', label: '分类观点' },
]

export default function ViewpointsPage() {
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
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center px-4 py-3">
          <h1 className="text-lg font-bold text-slate-800">观点库</h1>
          <div className="ml-auto flex items-center gap-4">
            <a
              href={`${EXPORT_BASE}/api/export/viewpoints`}
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              导出原始观点
            </a>
            <a
              href={`${EXPORT_BASE}/api/export/classified`}
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              导出分类观点
            </a>
            <Link
              to="/review"
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              审议工作台
            </Link>
            <Link to="/" className="text-sm text-slate-500 hover:text-slate-800">
              返回首页
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {view !== 'classified' && (
          <div className="rounded-lg bg-white p-4 shadow">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.layer}
              onChange={setFilter('layer')}
            >
              <option value="">全部分层</option>
              {LAYER_OPTIONS.map((label) => (
                <option key={label} value={LAYER_CODES[label]}>
                  {label}
                </option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.status}
              onChange={setFilter('status')}
            >
              <option value="">全部状态</option>
              {Object.entries(VIEWPOINT_STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.domain}
              onChange={setFilter('domain')}
            >
              <option value="">全部领域</option>
              {DOMAIN_OPTIONS.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.circle}
              onChange={setFilter('circle')}
            >
              <option value="">全部圈层</option>
              {CIRCLE_OPTIONS.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.discipline}
              onChange={setFilter('discipline')}
            >
              <option value="">全部学科</option>
              {DISCIPLINE_OPTIONS.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
            <select
              className="rounded border border-slate-300 px-2 py-1.5"
              value={filters.scene}
              onChange={setFilter('scene')}
            >
              <option value="">全部场景</option>
              {SCENE_OPTIONS.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
            <label className="text-slate-500">
              来源日期
              <input
                type="date"
                className="ml-1 rounded border border-slate-300 px-2 py-1"
                value={filters.date_from}
                onChange={setFilter('date_from')}
              />
              <span className="mx-1">至</span>
              <input
                type="date"
                className="rounded border border-slate-300 px-2 py-1"
                value={filters.date_to}
                onChange={setFilter('date_to')}
              />
            </label>
            <input
              className="w-48 rounded border border-slate-300 px-3 py-1.5 outline-none focus:border-slate-500"
              placeholder="关键词"
              value={filters.keyword}
              onChange={setFilter('keyword')}
            />
            <button
              className="rounded border border-slate-300 px-3 py-1.5 text-slate-500 hover:text-slate-800"
              onClick={() => setFilters(EMPTY_FILTERS)}
            >
              重置
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
              {tab.label}
            </button>
          ))}
          <span className="ml-auto text-sm text-slate-500">
            {view === 'classified' ? '' : `共 ${items.length} 条`}
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
                  <th className="px-3 py-2">编号</th>
                  <th className="px-3 py-2">正文</th>
                  <th className="px-3 py-2">分层</th>
                  <th className="px-3 py-2">标签</th>
                  <th className="px-3 py-2">状态</th>
                  <th className="px-3 py-2">来源日期</th>
                  <th className="px-3 py-2">入库时间</th>
                  <th className="px-3 py-2">操作</th>
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
                      {summarize(item.content, 60)}
                    </td>
                    <td className="px-3 py-2">
                      {LAYER_LABELS[item.layer] ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {tagLine(item) || '—'}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {item.source_date ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {formatDateTime(item.created_at)}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        className="text-sm text-slate-800 hover:underline"
                        onClick={() => setSelectedId(item.id)}
                      >
                        详情
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {items.length === 0 && (
              <p className="p-6 text-center text-sm text-slate-400">
                没有符合筛选条件的观点
              </p>
            )}
          </div>
        ) : (
          <ul className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <li key={item.id} className="rounded-lg bg-white p-4 shadow">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <span className="font-mono text-slate-400">#{item.id}</span>
                  <span>{LAYER_LABELS[item.layer] ?? '未分层'}</span>
                  <StatusBadge status={item.status} />
                </div>
                <p className="mt-2 text-slate-800">
                  {summarize(item.content, 120)}
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  {tagLine(item) || '无标签'} · 来源日期：
                  {item.source_date ?? '—'}
                </p>
                <button
                  className="mt-2 text-sm text-slate-800 hover:underline"
                  onClick={() => setSelectedId(item.id)}
                >
                  详情
                </button>
              </li>
            ))}
            {items.length === 0 && (
              <li className="rounded-lg bg-white p-6 text-center text-sm text-slate-400 shadow">
                没有符合筛选条件的观点
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
