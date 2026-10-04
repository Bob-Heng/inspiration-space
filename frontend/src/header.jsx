import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import PageHeader from './components/PageHeader'

/* 页头独立于页面切换过渡：各页面用 usePageHeader 注册自己的页头内容，
 * HeaderShell 在过渡容器之外渲染；extras 按 hk 交叉淡化（旧页独有淡出、
 * 新页独有淡入，共有项如语言切换保持不动）。 */

const HeaderCtx = createContext(null)

function ExtrasSwitcher({ items }) {
  // 合并序列渲染：旧序位置保持（出场项原地淡出），入场项按新序插入到其后
  // 首个驻留项之前（同时做宽度展开），任何按钮位置不跳变
  const [merged, setMerged] = useState(() =>
    items.map((i) => ({ ...i, entering: false, leaving: false })),
  )
  const itemsKey = items.map((i) => i.hk).join(',')
  const prevKeyRef = useRef(itemsKey)

  useEffect(() => {
    if (prevKeyRef.current === itemsKey) return undefined
    prevKeyRef.current = itemsKey
    const id = setTimeout(() => {
      const newHks = new Set(items.map((i) => i.hk))
      // 1) 旧序：在新集合中的驻留（换新 node），不在的原地标记 leaving
      let next = merged.map((p) =>
        newHks.has(p.hk)
          ? { ...items.find((i) => i.hk === p.hk), entering: false, leaving: false }
          : { ...p, leaving: true },
      )
      // 2) 新项：插入到"新顺序中其后第一个驻留项"之前，否则追加到末尾
      for (const it of items) {
        if (next.some((m) => m.hk === it.hk)) continue
        const anchor = items
          .slice(items.indexOf(it) + 1)
          .find((n) => next.some((m) => m.hk === n.hk && !m.leaving))
        const entry = { ...it, entering: true, leaving: false }
        if (anchor) {
          const idx = next.findIndex((m) => m.hk === anchor.hk)
          next = [...next.slice(0, idx), entry, ...next.slice(idx)]
        } else {
          next = [...next, entry]
        }
      }
      setMerged(next)
      const leavingHks = next.filter((m) => m.leaving).map((m) => m.hk)
      setTimeout(() => {
        setMerged((prev) =>
          prev
            .filter((p) => !(p.leaving && leavingHks.includes(p.hk)))
            .map((p) => ({ ...p, entering: false })),
        )
      }, 400)
    }, 0)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [itemsKey])

  return (
    <>
      {merged.map((i) => (
        <span
          key={i.hk}
          className={i.leaving ? 'hh-x--leave' : i.entering ? 'hh-x hh-grow' : ''}
        >
          {i.node}
        </span>
      ))}
    </>
  )
}

export function HeaderProvider({ children }) {
  const [reg, setReg] = useState(null)
  const value = useMemo(() => ({ setReg }), [])
  return (
    <HeaderCtx.Provider value={value}>
      {reg && (
        <PageHeader
          current={reg.current}
          subtitle={reg.subtitle}
          slogan={reg.slogan}
          extras={<ExtrasSwitcher items={reg.items} />}
        />
      )}
      {children}
    </HeaderCtx.Provider>
  )
}

/** 页面注册页头：items 需用 useMemo 保持引用稳定（元素含 hk 与 node） */
// eslint-disable-next-line react(only-export-components)
export function usePageHeader({ current, subtitle, slogan = null, items = [] }) {
  const { setReg } = useContext(HeaderCtx)
  useEffect(() => {
    const id = setTimeout(() => setReg({ current, subtitle, slogan, items }), 0)
    return () => {
      clearTimeout(id)
      setTimeout(() => setReg(null), 0)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, subtitle, slogan, items])
}
