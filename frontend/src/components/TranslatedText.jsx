import { useState } from 'react'
import { useLang } from '../i18n'

/**
 * 双语内容展示（纯展示，零网络请求）：
 * - 按界面语言显示对应版本；内容原文语言与界面语言一致时不提供切换
 * - 「显示原始文本 / 显示译文」切换（仅在有另一种语言版本且当前非原文时可用）
 * - clamp 时默认省略到三行，提供 展开/收起
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

  const zh = contentZh ?? contentEn ?? ''
  const en = contentEn ?? contentZh ?? ''
  // 只有两个版本都存在且不同、且当前显示的不是原文语言时，切换按钮才有意义
  const canToggle =
    contentZh && contentEn && contentZh !== contentEn && originalLang !== lang

  let display
  if (showOriginal && canToggle) {
    display = originalLang === 'en' ? en : zh
  } else {
    display = lang === 'en' ? en : zh
  }
  if (max && !expanded && display.length > max) {
    display = `${display.slice(0, max)}…`
  }

  return (
    <span className={className}>
      <span className={clamp && !expanded ? 'line-clamp-3' : undefined}>
        {display}
      </span>
      {clamp && (
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
