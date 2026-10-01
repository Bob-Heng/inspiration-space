import { useLang } from '../../i18n'
import { statusLabel } from '../../vocab'
import ItemTitle from '../ItemTitle'
import TranslatedText from '../TranslatedText'

export default function ReviewQueue({ items, selectedId, onSelect, error }) {
  const { t, tf, lang } = useLang()
  return (
    <div className="rounded-lg bg-white p-4 shadow">
      <h2 className="text-sm font-bold text-slate-800">{t('queue')}</h2>
      <p className="mt-1 text-xs text-slate-400">{tf('totalItems', { n: items.length })}</p>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li key={item.id}>
            <button
              className={`w-full rounded border p-3 text-left text-sm ${
                selectedId === item.id
                  ? 'border-slate-800 bg-slate-100'
                  : 'border-slate-200 hover:border-slate-400'
              }`}
              onClick={() => onSelect(item.id)}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-slate-400">#{item.id}</span>
                <span className="rounded bg-slate-200 px-1.5 py-0.5 text-xs text-slate-600">
                  {statusLabel(item.status, lang)}
                </span>
              </div>
              <ItemTitle titleZh={item.title_zh} titleEn={item.title_en} id={item.id} />
              <p className="mt-1 text-slate-800">
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
          <li className="py-6 text-center text-xs text-slate-400">{t('queueEmpty')}</li>
        )}
      </ul>
    </div>
  )
}
