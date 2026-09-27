import { useEffect, useState } from 'react'
import { api } from '../../api'

/**
 * AI 服务设置卡片：选择服务商 → 填 API Key → 测试连接拉取可用模型 → 下拉选择模型 → 保存。
 * 界面配置保存后立即生效，优先于环境变量；密钥只回显末 4 位。
 */
export default function LlmSettingsCard() {
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
    setMessage({ ok: false, text: '切换服务商后需重新填写 API Key 并测试连接' })
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
      setMessage({ ok: true, text: '已保存，立即生效' })
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
          ? `${result.message}，请在下方选择模型`
          : result.message,
      })
    } catch (err) {
      setMessage({ ok: false, text: err.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg bg-white p-4 shadow">
      <button
        className="flex w-full items-center text-sm font-bold text-slate-800"
        onClick={() => setOpen(!open)}
      >
        AI 服务设置
        <span className="ml-auto text-xs font-normal text-slate-400">
          {loading
            ? '加载中…'
            : effective
              ? `${effective.label}${effective.model ? ` · ${effective.model}` : ''}${effective.source === 'env' ? '（环境变量）' : ''}`
              : '未配置'}
          {open ? ' ▲' : ' ▼'}
        </span>
      </button>

      {open && (
        <div className="mt-3 space-y-3 text-sm">
          <label className="block">
            <span className="text-slate-500">服务商</span>
            <select
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
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
            <span className="text-slate-500">API Key</span>
            <input
              type="password"
              className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
              placeholder={
                savedKeyMasked
                  ? `已保存密钥 ${savedKeyMasked}，留空表示不变`
                  : '留空则保持已保存的密钥'
              }
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value)
                invalidateModels()
              }}
              autoComplete="off"
            />
            {savedKeyMasked && (
              <span className="mt-1 block text-xs text-slate-400">
                当前已保存密钥：{savedKeyMasked}（保存后输入框清空属正常，密钥仍在）
              </span>
            )}
          </label>

          {providerKey === 'custom' && (
            <label className="block">
              <span className="text-slate-500">Base URL</span>
              <input
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
                placeholder="如 http://localhost:3000/v1"
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
              <span className="text-slate-500">模型（从服务端拉取）</span>
              <select
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5"
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
            <p className={message.ok ? 'text-green-600' : 'text-red-600'}>
              {message.text}
            </p>
          )}

          <div className="flex gap-2">
            <button
              className="rounded border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50"
              onClick={handleTest}
              disabled={busy}
            >
              测试连接
            </button>
            <button
              className="rounded bg-slate-800 px-3 py-1.5 text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={handleSave}
              disabled={busy || (models.length > 0 && !model)}
            >
              保存
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
