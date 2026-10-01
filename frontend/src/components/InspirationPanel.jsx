import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import ItemTitle from './ItemTitle'
import TranslatedText from './TranslatedText'
import { useLang } from '../i18n'
import { statusLabel } from '../vocab'

/**
 * 灵感录入与队列组件。可复用：嵌入首页与后续审议工作台，不设独立灵感页。
 * 含 docx 导入（TASK-018）：上传 → AI 拆解预览 → 勾选/编辑 → 确认入库。
 */
export default function InspirationPanel() {
  const navigate = useNavigate()
  const { t, tf, lang } = useLang()
  const [items, setItems] = useState([])
  const [content, setContent] = useState('')
  const [sourceDate, setSourceDate] = useState('')
  const [keyword, setKeyword] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [error, setError] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editingContent, setEditingContent] = useState('')
  const fileInputRef = useRef(null)
  const [importing, setImporting] = useState(false)
  const [confirming, setConfirming] = useState(false)
  // 预览项：{ content, source_date, selected }
  const [preview, setPreview] = useState(null)
  const [renameTarget, setRenameTarget] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [renameLang, setRenameLang] = useState('zh')
  const [renameSubmitting, setRenameSubmitting] = useState(false)
  const [renameError, setRenameError] = useState(null)

  const load = useCallback(async () => {
    try {
      const data = await api.listInspirations({
        status: statusFilter || undefined,
        keyword: keyword || undefined,
      })
      setItems(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [statusFilter, keyword])

  useEffect(() => {
    load()
  }, [load])

  async function handleCreate(e) {
    e.preventDefault()
    if (!content.trim()) return
    try {
      await api.createInspiration({
        content: content.trim(),
        source_date: sourceDate || new Date().toLocaleDateString('sv-SE'),
      })
      setContent('')
      setSourceDate('')
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleFileChosen(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setImporting(true)
    setError(null)
    try {
      const data = await api.importDocxPreview(file)
      setPreview({
        filename: data.filename,
        items: data.items.map((item) => ({
          content: item.content,
          source_date: item.source_date ?? '',
          selected: true,
        })),
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setImporting(false)
    }
  }

  function updatePreviewItem(index, patch) {
    setPreview((prev) => ({
      ...prev,
      items: prev.items.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    }))
  }

  async function handleConfirmImport() {
    const chosen = preview.items
      .filter((item) => item.selected && item.content.trim())
      .map((item) => ({
        content: item.content.trim(),
        source_date: item.source_date || null,
      }))
    if (chosen.length === 0) return
    setConfirming(true)
    setError(null)
    try {
      await api.confirmImport(chosen)
      setPreview(null)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setConfirming(false)
    }
  }

  async function handleSaveEdit(id) {
    if (!editingContent.trim()) return
    try {
      await api.updateInspiration(id, { content: editingContent.trim() })
      setEditingId(null)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(id) {
    if (!window.confirm(tf('deleteConfirm', { id }))) return
    try {
      await api.deleteInspiration(id)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  function openRename(item) {
    setRenameTarget(item)
    setRenameValue(
      lang === 'en'
        ? (item.title_en ?? item.title_zh ?? '')
        : (item.title_zh ?? item.title_en ?? ''),
    )
    setRenameLang(lang)
    setRenameError(null)
  }

  async function handleRenameSubmit(e) {
    e.preventDefault()
    if (!renameTarget || !renameValue.trim()) return
    setRenameSubmitting(true)
    setRenameError(null)
    try {
      await api.renameTitle(renameTarget.id, renameValue.trim(), renameLang)
      setRenameTarget(null)
      await load()
    } catch (err) {
      setRenameError(err.message)
    } finally {
      setRenameSubmitting(false)
    }
  }

  const selectedCount = preview?.items.filter((item) => item.selected).length ?? 0

  return (
    <div className="space-y-6">
      <form onSubmit={handleCreate} className="rounded-lg bg-white p-4 shadow">
        <textarea
          className="w-full rounded border border-slate-300 p-3 outline-none focus:border-slate-500"
          rows={3}
          placeholder={t('recordPlaceholder')}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <div className="mt-2 flex items-center gap-3">
          <label className="text-sm text-slate-500">
            {t('sourceDateOptional')}
            <input
              type="date"
              className="ml-2 rounded border border-slate-300 px-2 py-1"
              value={sourceDate}
              onChange={(e) => setSourceDate(e.target.value)}
            />
          </label>
          <button
            type="submit"
            className="ml-auto rounded bg-slate-800 px-4 py-2 text-sm text-white hover:bg-slate-700"
          >
            {t('addToQueue')}
          </button>
          <button
            type="button"
            disabled={importing}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            onClick={() => fileInputRef.current?.click()}
          >
            {importing ? t('importing') : t('importDocx')}
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".docx"
            className="hidden"
            onChange={handleFileChosen}
          />
        </div>
      </form>

      {preview && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 shadow">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-slate-800">
              {tf('importPreview', {
                name: preview.filename,
                total: preview.items.length,
                n: selectedCount,
              })}
            </h2>
            <div className="ml-auto flex gap-2">
              <button
                disabled={confirming || selectedCount === 0}
                className="rounded bg-slate-800 px-4 py-2 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                onClick={handleConfirmImport}
              >
                {confirming ? t('confirmingImport') : tf('confirmImport', { n: selectedCount })}
              </button>
              <button
                disabled={confirming}
                className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-white"
                onClick={() => setPreview(null)}
              >
                {t('cancel')}
              </button>
            </div>
          </div>
          <p className="mt-1 text-xs text-slate-500">{t('importHint')}</p>
          <ul className="mt-3 space-y-2">
            {preview.items.map((item, index) => (
              <li
                key={index}
                className={`rounded border p-3 ${
                  item.selected ? 'border-slate-300 bg-white' : 'border-slate-200 bg-slate-50 opacity-60'
                }`}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={item.selected}
                    onChange={(e) => updatePreviewItem(index, { selected: e.target.checked })}
                  />
                  <div className="min-w-0 flex-1 space-y-2">
                    <textarea
                      className="w-full rounded border border-slate-200 p-2 text-sm outline-none focus:border-slate-500"
                      rows={Math.min(6, Math.max(2, item.content.split('\n').length + 1))}
                      value={item.content}
                      onChange={(e) => updatePreviewItem(index, { content: e.target.value })}
                    />
                    <label className="block text-xs text-slate-500">
                      {t('colSourceDate')}
                      <input
                        type="date"
                        className="ml-2 rounded border border-slate-300 px-2 py-0.5"
                        value={item.source_date}
                        onChange={(e) => updatePreviewItem(index, { source_date: e.target.value })}
                      />
                    </label>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-3">
        <input
          className="w-64 rounded border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-slate-500"
          placeholder={t('keywordSearch')}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <select
          className="rounded border border-slate-300 px-2 py-1.5 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">{t('allStatus')}</option>
          <option value="pending">{statusLabel('pending', lang)}</option>
          <option value="in_review">{statusLabel('in_review', lang)}</option>
          <option value="reviewed">{statusLabel('reviewed', lang)}</option>
          <option value="rejected">{statusLabel('rejected', lang)}</option>
        </select>
        <span className="text-sm text-slate-500">{tf('totalItems', { n: items.length })}</span>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id} className="rounded-lg bg-white p-4 shadow">
            {editingId === item.id ? (
              <div>
                <textarea
                  className="w-full rounded border border-slate-300 p-2 outline-none focus:border-slate-500"
                  rows={3}
                  value={editingContent}
                  onChange={(e) => setEditingContent(e.target.value)}
                />
                <div className="mt-2 flex gap-2">
                  <button
                    className="rounded bg-slate-800 px-3 py-1 text-sm text-white"
                    onClick={() => handleSaveEdit(item.id)}
                  >
                    {t('save')}
                  </button>
                  <button
                    className="rounded border border-slate-300 px-3 py-1 text-sm"
                    onClick={() => setEditingId(null)}
                  >
                    {t('cancel')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <span className="shrink-0 font-mono text-sm text-slate-400">
                  #{item.id}
                </span>
                <div className="min-w-0 flex-1">
                  <ItemTitle titleZh={item.title_zh} titleEn={item.title_en} id={item.id} />
                  <p className="text-slate-800">
                    <TranslatedText
                      contentZh={item.content_zh}
                      contentEn={item.content_en}
                      originalLang={item.original_lang}
                      clamp
                    />
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {item.source_date ?? t('noSourceDateFull')} ·{' '}
                    {statusLabel(item.status, lang)}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  {(item.status === 'pending' || item.status === 'in_review') && (
                    <button
                      className="text-sm text-slate-800 hover:underline"
                      onClick={() => navigate(`/review?inspiration=${item.id}`)}
                    >
                      {t('startReview')}
                    </button>
                  )}
                  <button
                    className="text-sm text-slate-500 hover:text-slate-800"
                    onClick={() => {
                      setEditingId(item.id)
                      setEditingContent(item.content)
                    }}
                  >
                    {t('edit')}
                  </button>
                  <button
                    className="text-sm text-slate-500 hover:text-slate-800"
                    onClick={() => openRename(item)}
                  >
                    {t('rename')}
                  </button>
                  <button
                    className="text-sm text-red-500 hover:text-red-700"
                    onClick={() => handleDelete(item.id)}
                  >
                    {t('delete')}
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
        {items.length === 0 && (
          <li className="rounded-lg bg-white p-6 text-center text-sm text-slate-400 shadow">
            {t('queueEmpty')}
          </li>
        )}
      </ul>

      {renameTarget && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/30 p-4">
          <form
            className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
            onSubmit={handleRenameSubmit}
          >
            <h3 className="text-sm font-bold text-slate-800">{t('renameDialogTitle')}</h3>
            <input
              className="mt-3 w-full rounded border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-500"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder={t('renamePlaceholder')}
              autoFocus
            />
            <div className="mt-3 flex items-center gap-4 text-sm text-slate-600">
              <span className="text-xs text-slate-500">{t('renameLangLabel')}</span>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  checked={renameLang === 'zh'}
                  onChange={() => setRenameLang('zh')}
                />
                中文
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  checked={renameLang === 'en'}
                  onChange={() => setRenameLang('en')}
                />
                English
              </label>
            </div>
            {renameError && <p className="mt-2 text-sm text-red-600">{renameError}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                onClick={() => setRenameTarget(null)}
                disabled={renameSubmitting}
              >
                {t('cancel')}
              </button>
              <button
                type="submit"
                className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
                disabled={renameSubmitting || !renameValue.trim()}
              >
                {renameSubmitting ? t('renaming') : t('confirm')}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
