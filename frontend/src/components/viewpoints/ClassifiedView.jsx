import { useCallback, useEffect, useState } from 'react'
import { api } from '../../api'
import { StatusBadge } from '../../pages/ViewpointsPage'
import { LAYER_LABELS, tagLine } from '../../vocab'

const GROUPS = ['dao', 'fa', 'shu']

export default function ClassifiedView({ onSelect }) {
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

  if (error) return <p className="mt-4 text-sm text-red-600">{error}</p>
  if (!groups) return <p className="mt-4 text-sm text-slate-400">加载中…</p>

  return (
    <div className="mt-4 space-y-4">
      <p className="text-xs text-slate-400">
        已否定不列入；已悬置保留并带标记；组内按来源日期排序。
      </p>
      {GROUPS.map((layer) => (
        <section key={layer} className="rounded-lg bg-white p-4 shadow">
          <h2 className="text-sm font-bold text-slate-800">
            {LAYER_LABELS[layer]}
            <span className="ml-2 text-xs font-normal text-slate-400">
              {groups[layer].length} 条
            </span>
          </h2>
          {groups[layer].length === 0 ? (
            <p className="mt-2 text-sm text-slate-400">暂无。</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {groups[layer].map((item) => (
                <li
                  key={item.id}
                  className="rounded border border-slate-200 p-3 text-sm"
                >
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span className="font-mono text-slate-400">#{item.id}</span>
                    <StatusBadge status={item.status} />
                    <span>{item.source_date ?? '无来源日期'}</span>
                    <button
                      className="ml-auto text-slate-800 hover:underline"
                      onClick={() => onSelect(item.id)}
                    >
                      详情
                    </button>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-slate-800">
                    {item.content}
                  </p>
                  {tagLine(item) && (
                    <p className="mt-1 text-xs text-slate-500">{tagLine(item)}</p>
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
