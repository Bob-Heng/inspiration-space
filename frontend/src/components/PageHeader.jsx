import { Link } from 'react-router-dom'
import { useLang } from '../i18n'

const NAV = [
  { key: 'home', to: '/', labelKey: 'home' },
  { key: 'review', to: '/review', labelKey: 'reviewWorkbench' },
  { key: 'viewpoints', to: '/viewpoints', labelKey: 'viewpointLibrary' },
]

/**
 * 统一页头：灵感空间 + 大斜杠 + 副标题（略小、略淡、位置更靠下且与标题交错）。
 * 导航固定为 首页/审议工作台/观点库，位置跨页一致（当前页高亮不可点）；
 * 页面特有按钮放右侧固定宽度区，不影响导航位置。
 */
export default function PageHeader({ current, subtitle, extras = null }) {
  const { t } = useLang()
  return (
    <header className="shrink-0 border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center px-4 py-3">
        <div className="flex items-start">
          <h1 className="text-lg font-bold leading-none text-slate-800">
            {t('appName')}
          </h1>
          <span
            aria-hidden
            className="-ml-0.5 -mt-1 text-[34px] font-light leading-none text-slate-400"
          >
            /
          </span>
          <span className="-ml-1 mt-4 text-xs leading-none text-slate-500">
            {subtitle}
          </span>
        </div>
        <nav className="ml-auto flex items-center gap-4">
          {NAV.map((item) =>
            item.key === current ? (
              <span
                key={item.key}
                className="text-sm font-medium text-slate-800"
              >
                {t(item.labelKey)}
              </span>
            ) : (
              <Link
                key={item.key}
                to={item.to}
                className="text-sm text-slate-500 hover:text-slate-800"
              >
                {t(item.labelKey)}
              </Link>
            ),
          )}
          {/* 页面特有按钮的固定宽度区：保证导航三键跨页位置不动 */}
          <div className="flex w-64 items-center justify-end gap-3">{extras}</div>
        </nav>
      </div>
    </header>
  )
}
