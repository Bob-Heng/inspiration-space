import { useEffect, useRef, useState } from 'react'
import { useLang } from '../../i18n'
import ItemTitle from '../ItemTitle'
import SortToggle from '../SortToggle'
import PhaseBadge from '../PhaseBadge'
import TranslatedText from '../TranslatedText'

export default function ReviewQueue({ items, selectedId, onSelect, error }) {
  const { t, tf } = useLang()
  const itemRefs = useRef(new Map())
  const [sortOrder, setSortOrder] = useState('asc')
  const sorted = [...items].sort((a, b) => {
    const da = a.inspiration_id ?? a.id
    const db = b.inspiration_id ?? b.id
    return sortOrder === 'asc' ? da - db : db - da
  })

  // 打开打磨（含从首页跳转、恢复会话）时，队列自动滚动到选中的观点。
  // 等目标条目真实渲染后只滚一次：双 rAF 让行内异步测量（如 clamp 的展开按钮）
  // 完成后再定位，避免先滚到过期位置再二次纠正（跳动）。
  useEffect(() => {
    if (selectedId == null) return
    if (!itemRefs.current.has(selectedId)) return
    let inner
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => {
        itemRefs.current.get(selectedId)?.scrollIntoView({ block: 'nearest' })
      })
    })
    return () => {
      cancelAnimationFrame(outer)
      if (inner) cancelAnimationFrame(inner)
    }
  }, [selectedId, items])

  return (
    <div className="ui-card p-4">
      <div className="flex items-center">
        <h2 className="text-sm font-bold text-ink">{t('queue')}</h2>
        <SortToggle className="ml-2" order={sortOrder} onChange={setSortOrder} />
      </div>
      <p className="mt-1 text-xs text-ink-3">{tf('totalItems', { n: items.length })}</p>
      {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      <ul className="mt-3 space-y-2">
        {sorted.map((item) => (
          <li
            key={item.id}
            ref={(el) => {
              if (el) itemRefs.current.set(item.id, el)
              else itemRefs.current.delete(item.id)
            }}
          >
            <button
              className={`w-full rounded border p-3 text-left text-sm transition-colors duration-200 ${
                selectedId === item.id
                  ? 'border-accent bg-accent-soft'
                  : 'border-rule hover:bg-paper-2'
              }`}
              onClick={() => onSelect(item.id)}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-accent">#{item.inspiration_id ?? item.id}</span>
                <PhaseBadge phase={item.phase} />
              </div>
              <ItemTitle titleZh={item.title_zh} titleEn={item.title_en} id={item.id} />
              <p className="mt-1 text-ink">
                <TranslatedText
                  contentZh={item.content_zh}
                  contentEn={item.content_en}
                  originalLang={item.original_lang}
                  clamp
                />
              </p>
            </button>
          </li>
        ))}
        {items.length === 0 && (
          <li className="py-6 text-center text-xs text-ink-3">{t('queueEmpty')}</li>
        )}
      </ul>
    </div>
  )
}
