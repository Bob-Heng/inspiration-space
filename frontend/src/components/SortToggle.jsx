import { useLang } from '../i18n'

/** 正序/倒序切换按钮（按观点编号排序）。 */
export default function SortToggle({ order, onChange, className = '' }) {
  const { t } = useLang()
  return (
    <button
      type="button"
      className={`rounded border border-rule px-2 py-0.5 text-xs text-ink-3 hover:text-ink ${className}`}
      onClick={() => onChange(order === 'asc' ? 'desc' : 'asc')}
      title={order === 'asc' ? t('sortAsc') : t('sortDesc')}
    >
      {order === 'asc' ? `↑ ${t('sortAsc')}` : `↓ ${t('sortDesc')}`}
    </button>
  )
}
