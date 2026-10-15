import { useMemo } from 'react'
import LlmSettingsCard from '../components/review/LlmSettingsCard'
import { usePageHeader } from '../header'
import { LangSelect, useLang } from '../i18n'

export default function SettingsPage() {
  const { t } = useLang()
  const items = useMemo(() => [{ hk: 'lang', node: <LangSelect /> }], [])
  usePageHeader({ current: 'settings', subtitle: t('aiSettings'), items })

  return (
    <main className="mx-auto max-w-2xl space-y-4 px-4 py-8">
      <h2 className="text-lg font-bold text-ink">{t('aiSettings')}</h2>
      <p className="text-sm text-ink-2">{t('aiSetupHint')}</p>
      <LlmSettingsCard defaultOpen />
    </main>
  )
}
