import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useLang } from '../../i18n'

/**
 * AI 服务设置卡片：选择服务商 → 填 API Key → 测试连接拉取可用模型 → 下拉选择模型 → 保存。
 * 界面配置保存后立即生效，优先于环境变量；密钥只回显末 4 位。
 */
export default function LlmSettingsCard() {
  const { t, tf } = useLang()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [presets, setPresets] = useState([])
  const [effective, setEffective] = useState(null)
  const [savedModel, setSavedModel] = useState(null)
  const [providerKey, setProviderKey] = useState('openai')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [savedKeyMasked, setSavedKeyMasked] = useState(null)
  const [models, setModels] = useState([])
  const [model, setModel] = useState('')
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api
      .getLlmSettings()
      .then((data) => {
        setPresets(data.presets ?? [])
        setEffective(data.effective ?? null)
        const saved = data.saved
        if (saved) {
          setProviderKey(saved.provider_key)
          setBaseUrl(saved.base_url ?? '')
          setSavedModel(saved.model ?? null)
          setSavedKeyMasked(saved.has_api_key ? saved.api_key_masked : null)
          if (saved.model) setModel(saved.model)
        } else if (data.effective && data.effective.source === 'ui') {
          setProviderKey(data.effective.provider_key)
          setBaseUrl(data.effective.base_url ?? '')
        }
      })
      .catch((err) => setMessage({ ok: false, text: err.message }))
      .finally(() => setLoading(false))
  }, [])

  function invalidateModels() {
    setModels([])
    setModel('')
  }

  function handleProviderChange(key) {
    setProviderKey(key)
    if (key !== 'custom') setBaseUrl('')
    setApiKey('')
    invalidateModels()
    setMessage({ ok: false, text: t('switchProviderNote') })
  }

  async function handleSave() {
    setBusy(true)
    setMessage(null)
    try {
      const data = await api.saveLlmSettings({
        provider_key: providerKey,
        base_url: providerKey === 'custom' ? baseUrl || null : null,
        api_key: apiKey || null,
        model: model || null,
      })
      setEffective(data.effective)
      setSavedModel(data.saved?.model ?? null)
      setSavedKeyMasked(
        data.saved?.has_api_key ? data.saved.api_key_masked : null,
      )
      setApiKey('')
      setMessage({ ok: true, text: t('savedOk') })
    } catch (err) {
      setMessage({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  async function handleTest() {
    setBusy(true)
    setMessage(null)
    invalidateModels()
    try {
      const result = await api.testLlmSettings({
        provider_key: providerKey,
        base_url: providerKey === 'custom' ? baseUrl || null : null,
        api_key: apiKey || null,
      })
      if (result.ok) {
        const list = result.models ?? []
        setModels(list)
        setModel(savedModel && list.includes(savedModel) ? savedModel : (list[0] ?? ''))
      }
      setMessage({
        ok: result.ok,
        text: result.models?.length
          ? tf('testOkPickModel', { msg: result.message })
          : result.message,
      })
    } catch (err) {
      setMessage({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ui-card p-4">
      <button
        className="flex w-full items-center text-sm font-bold text-ink"
        onClick={() => setOpen(!open)}
      >
        {t('aiSettings')}
        <span className="ml-auto text-xs font-normal text-ink-3">
          {loading
            ? t('loading')
            : effective
              ? `${effective.label}${effective.model ? ` · ${effective.model}` : ''}${effective.source === 'env' ? t('envSource') : ''}`
              : t('notConfigured')}
          {open ? ' ▲' : ' ▼'}
        </span>
      </button>

      {open && (
        <div className="mt-3 space-y-3 text-sm">
          <label className="block">
            <span className="text-ink-2">{t('provider')}</span>
            <select
              className="ui-input mt-1 w-full px-2 py-1.5"
              value={providerKey}
              onChange={(e) => handleProviderChange(e.target.value)}
            >
              {presets.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-ink-2">{t('apiKey')}</span>
            <input
              type="password"
              className="ui-input mt-1 w-full px-2 py-1.5"
              placeholder={
                savedKeyMasked
                  ? tf('apiKeyPlaceholderSaved', { masked: savedKeyMasked })
                  : t('apiKeyPlaceholderNew')
              }
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value)
                invalidateModels()
              }}
              autoComplete="off"
            />
            {savedKeyMasked && (
              <span className="mt-1 block text-xs text-ink-3">
                {tf('apiKeySavedNote', { masked: savedKeyMasked })}
              </span>
            )}
          </label>

          {providerKey === 'custom' && (
            <label className="block">
              <span className="text-ink-2">{t('baseUrl')}</span>
              <input
                className="ui-input mt-1 w-full px-2 py-1.5"
                placeholder={t('baseUrlPlaceholder')}
                value={baseUrl}
                onChange={(e) => {
                  setBaseUrl(e.target.value)
                  invalidateModels()
                }}
              />
            </label>
          )}

          {models.length > 0 && (
            <label className="block">
              <span className="text-ink-2">{t('modelLabel')}</span>
              <select
                className="ui-input mt-1 w-full px-2 py-1.5"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          )}

          {message && (
            <p className={message.ok ? 'text-accent' : 'text-danger'}>
              {message.text}
            </p>
          )}

          <div className="flex gap-2">
            <button
              className="ui-btn-ghost px-3 py-1.5"
              onClick={handleTest}
              disabled={busy}
            >
              {t('testConnection')}
            </button>
            <button
              className="ui-btn-primary px-3 py-1.5"
              onClick={handleSave}
              disabled={busy || (models.length > 0 && !model)}
            >
              {t('save')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
