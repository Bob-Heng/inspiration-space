import { useLang } from '../i18n'

/**
 * 灵感/观点的双语标题：按界面语言显示对应版本。
 * 当前语言版本缺失（大模型未接入）时显示「标题待生成，等待大模型接入……」，
 * 不拿另一语言的标题冒充。与正文同字号、加粗。
 */
export default function ItemTitle({ titleZh, titleEn, id, className = '' }) {
  const { lang, t } = useLang()
  const title = lang === 'en' ? titleEn : titleZh
  if (!titleZh && !titleEn) {
    return (
      <p data-item-id={id} className={`mt-1.5 font-semibold text-slate-400 ${className}`}>
        {t('pendingTitle')}
      </p>
    )
  }
  return (
    <p data-item-id={id} className={`mt-1.5 font-semibold ${className}`}>
      {title ?? t('pendingTitle')}
    </p>
  )
}
