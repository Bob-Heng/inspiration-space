import { useLayoutEffect, useRef, useState } from 'react'
import { useLang } from '../i18n'

/**
 * 双语内容展示（纯展示，零网络请求）：
 * - 按界面语言显示对应版本；原文语言与界面语言一致时直接显示原文
 * - 所需语言版本缺失（大模型未接入）时显示「暂无法翻译，等待大模型接入……」
 * - 双语齐全时可「显示原始文本 / 显示译文」切换（原文语言=界面语言时不显示按钮）
 * - clamp 时默认省略到三行；仅当内容实际溢出三行才显示 展开/收起
 */
export default function TranslatedText({
  contentZh,
  contentEn,
  originalLang = 'zh',
  max,
  clamp = false,
  className = '',
}) {
  const { lang, t } = useLang()
  const [showOriginal, setShowOriginal] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [overflowing, setOverflowing] = useState(false)
  const textRef = useRef(null)

  const current = lang === 'en' ? contentEn : contentZh
  const original = originalLang === 'en' ? contentEn : contentZh
  const bothReady = contentZh && contentEn
  const canToggle = Boolean(bothReady) && originalLang !== lang

  let display
  if (showOriginal && canToggle) {
    display = original
  } else if (current != null) {
    display = current
  } else if (originalLang === lang && original != null) {
    display = original // 原文即当前语言，无需翻译
  } else {
    display = t('pendingTranslation') // 兜底表述：不拿原文冒充译文
  }
  if (max && !expanded && display.length > max) {
    display = `${display.slice(0, max)}…`
  }

  // clamp 渲染后测量三行是否真溢出（+2px 容差），不溢出则不显示展开/收起
  useLayoutEffect(() => {
    if (!clamp || expanded) return
    const el = textRef.current
    if (!el) return
    const check = () => setOverflowing(el.scrollHeight > el.clientHeight + 2)
    const raf = requestAnimationFrame(check)
    const observer = new ResizeObserver(check)
    observer.observe(el)
    return () => {
      cancelAnimationFrame(raf)
      observer.disconnect()
    }
  }, [clamp, expanded, display])

  return (
    <span className={className}>
      <span
        ref={textRef}
        className={clamp && !expanded ? 'line-clamp-3' : undefined}
      >
        {display}
      </span>
      {clamp && overflowing && (
        <button
          type="button"
          className="ml-2 text-xs text-slate-400 underline hover:text-slate-600"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? t('collapse') : t('expand')}
        </button>
      )}
      {canToggle && (
        <button
          type="button"
          className="ml-2 text-xs text-slate-400 underline hover:text-slate-600"
          onClick={() => setShowOriginal(!showOriginal)}
        >
          {showOriginal ? t('showTranslation') : t('showOriginal')}
        </button>
      )}
    </span>
  )
}
