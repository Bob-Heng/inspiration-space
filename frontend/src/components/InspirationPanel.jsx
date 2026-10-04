import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import ItemTitle from './ItemTitle'
import PhaseBadge from './PhaseBadge'
import SortToggle from './SortToggle'
import TranslatedText from './TranslatedText'
import { useLang } from '../i18n'
import { statusLabel } from '../vocab'

// 每页条数（客户端分页）
const PAGE_SIZE = 10

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
  const [deletingItem, setDeletingItem] = useState(null)
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
        keyword: keyword || undefined,
      })
      setItems(data)
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [keyword])

  useEffect(() => {
    load()
  }, [load])

  const listEndRef = useRef(null)

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
      // 录入后自动滚动到列表底部（新增灵感处）
      requestAnimationFrame(() =>
        listEndRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }),
      )
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

  async function handleSaveEdit(item) {
    if (!editingContent.trim()) return
    // 已关联观点且正文实际变化：编辑会使他山坊中的观点回退到提炼最开始
    // （讨论/分析清空），需确认；仅日期等变化不动观点，免弹窗直接保存
    const contentChanged = editingContent.trim() !== (item.content ?? '').trim()
    if (contentChanged && item.viewpoint_id && !window.confirm(t('editResetConfirm'))) return
    try {
      await api.updateInspiration(item.id, { content: editingContent.trim() })
      setEditingId(null)
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleConfirmDelete() {
    const item = deletingItem
    if (!item) return
    setDeletingItem(null)
    try {
      await api.deleteInspiration(item.id)
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

  // 状态筛选为前端过滤：accepted=已入库；distill/polish=对应阶段的 draft 观点
  const [sortOrder, setSortOrder] = useState('desc')
  const visibleItems = items.filter((item) => {
    if (!statusFilter) return true
    if (statusFilter === 'accepted') return item.viewpoint_status === 'accepted'
    return item.viewpoint_status === 'draft' && item.viewpoint_phase === statusFilter
  })

  const sortedItems = [...visibleItems].sort((a, b) =>
    sortOrder === 'asc' ? a.id - b.id : b.id - a.id,
  )

  // 客户端分页：筛选/搜索在事件里重置到第 1 页；录入/删除/编辑等导致总数变化时
  // 当前页在渲染期夹取到合法范围（state 里的旧页码可越界，展示一律用夹取值）
  const [page, setPage] = useState(1)
  const totalPages = Math.max(1, Math.ceil(sortedItems.length / PAGE_SIZE))
  const currentPage = Math.min(Math.max(1, page), totalPages)
  const pageItems = sortedItems.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  )

  function jumpToPage(value) {
    const v = parseInt(value, 10)
    if (Number.isNaN(v)) return
    setPage(Math.min(Math.max(1, v), totalPages))
  }

  return (
    <div className="space-y-6">
      <form onSubmit={handleCreate} className="ui-card p-5">
        <textarea
          className="ui-input w-full p-3"
          rows={3}
          placeholder={t('recordPlaceholder')}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        <div className="mt-3 flex items-center gap-3">
          <label className="text-sm text-ink-2">
            {t('sourceDateOptional')}
            <input
              type="date"
              className="ui-input ml-2 px-2 py-1"
              value={sourceDate}
              onChange={(e) => setSourceDate(e.target.value)}
            />
          </label>
          <button type="submit" className="ui-btn-gold ml-auto px-4 py-2 text-sm">
            {t('addToQueue')}
          </button>
          <button
            type="button"
            disabled={importing}
            className="ui-btn-ghost px-4 py-2 text-sm"
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
        <div className="rounded-card border border-accent-2 bg-accent-2-soft p-4 shadow-card">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-semibold text-ink">
              {tf('importPreview', {
                name: preview.filename,
                total: preview.items.length,
                n: selectedCount,
              })}
            </h2>
            <div className="ml-auto flex gap-2">
              <button
                disabled={confirming || selectedCount === 0}
                className="ui-btn-gold px-4 py-2 text-sm"
                onClick={handleConfirmImport}
              >
                {confirming ? t('confirmingImport') : tf('confirmImport', { n: selectedCount })}
              </button>
              <button
                disabled={confirming}
                className="ui-btn-ghost bg-white px-4 py-2 text-sm"
                onClick={() => setPreview(null)}
              >
                {t('cancel')}
              </button>
            </div>
          </div>
          <p className="mt-1 text-xs text-ink-2">{t('importHint')}</p>
          <ul className="mt-3 space-y-2">
            {preview.items.map((item, index) => (
              <li
                key={index}
                className={`rounded-input border p-3 ${
                  item.selected ? 'border-rule bg-white' : 'border-rule/60 bg-paper-2 opacity-60'
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
                      className="ui-input w-full p-2 text-sm"
                      rows={Math.min(6, Math.max(2, item.content.split('\n').length + 1))}
                      value={item.content}
                      onChange={(e) => updatePreviewItem(index, { content: e.target.value })}
                    />
                    <label className="block text-xs text-ink-2">
                      {t('colSourceDate')}
                      <input
                        type="date"
                        className="ui-input ml-2 px-2 py-0.5"
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
          className="ui-input w-64 px-3 py-1.5 text-sm"
          placeholder={t('keywordSearch')}
          value={keyword}
          onChange={(e) => {
            setKeyword(e.target.value)
            setPage(1)
          }}
        />
        <select
          className="ui-input px-2 py-1.5 text-sm"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(1)
          }}
        >
          <option value="">{t('allStatus')}</option>
          <option value="distill">{t('phaseDistill')}</option>
          <option value="polish">{t('phasePolish')}</option>
          <option value="accepted">{statusLabel('accepted', lang)}</option>
        </select>
        <span className="text-sm text-ink-2">
          {tf('totalItems', { n: visibleItems.length })}
        </span>
        <SortToggle order={sortOrder} onChange={setSortOrder} />
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      <ul className="ui-reveal space-y-2.5">
        {pageItems.map((item) => (
          <li key={item.id} className="ui-card p-4">
            {editingId === item.id ? (
              <div>
                <textarea
                  className="ui-input w-full p-2"
                  rows={3}
                  value={editingContent}
                  onChange={(e) => setEditingContent(e.target.value)}
                />
                <div className="mt-2 flex gap-2">
                  <button
                    className="ui-btn-primary px-3 py-1 text-sm"
                    onClick={() => handleSaveEdit(item)}
                  >
                    {t('save')}
                  </button>
                  <button
                    className="ui-btn-ghost px-3 py-1 text-sm"
                    onClick={() => setEditingId(null)}
                  >
                    {t('cancel')}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <span className="shrink-0 font-mono text-sm text-accent">
                  #{item.id}
                </span>
                <div className="min-w-0 flex-1">
                  <ItemTitle titleZh={item.title_zh} titleEn={item.title_en} id={item.id} />
                  <p className="text-ink">
                    <TranslatedText
                      contentZh={item.content_zh}
                      contentEn={item.content_en}
                      originalLang={item.original_lang}
                      clamp
                    />
                  </p>
                  <p className="mt-1 text-xs text-ink-3">
                    {item.source_date ?? t('noSourceDateFull')}
                    {item.viewpoint_status === 'accepted' && (
                      <span className="ml-2 rounded-pill bg-accent-soft px-2 py-0.5 text-accent">
                        {statusLabel('accepted', lang)}
                      </span>
                    )}
                    {item.viewpoint_status === 'draft' && (
                      <PhaseBadge phase={item.viewpoint_phase} className="ml-2" />
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  {item.viewpoint_status === 'draft' && item.viewpoint_id && (
                    <button
                      className="text-sm font-medium text-accent hover:underline"
                      onClick={() =>
                        navigate(`/review?viewpoint=${item.viewpoint_id}&auto=1`)
                      }
                    >
                      {t('startReview')}
                    </button>
                  )}
                  <span
                    title={
                      item.viewpoint_status === 'accepted'
                        ? t('adoptedEditLocked')
                        : undefined
                    }
                  >
                    <button
                      className={`ui-link text-sm${
                        item.viewpoint_status === 'accepted'
                          ? ' cursor-not-allowed opacity-40'
                          : ''
                      }`}
                      disabled={item.viewpoint_status === 'accepted'}
                      onClick={() => {
                        setEditingId(item.id)
                        setEditingContent(item.content)
                      }}
                    >
                      {t('edit')}
                    </button>
                  </span>
                  <button
                    className="ui-link text-sm"
                    onClick={() => openRename(item)}
                  >
                    {t('rename')}
                  </button>
                  <span
                    title={
                      item.viewpoint_status === 'accepted'
                        ? t('adoptedDeleteLocked')
                        : undefined
                    }
                  >
                    <button
                      className={`ui-link-danger text-sm${
                        item.viewpoint_status === 'accepted'
                          ? ' cursor-not-allowed opacity-40'
                          : ''
                      }`}
                      disabled={item.viewpoint_status === 'accepted'}
                      onClick={() => setDeletingItem(item)}
                    >
                      {t('delete')}
                    </button>
                  </span>
                </div>
              </div>
            )}
          </li>
        ))}
        {visibleItems.length === 0 && (
          <li className="ui-card p-6 text-center text-sm text-ink-3">
            {t('queueEmpty')}
          </li>
        )}
        <li ref={listEndRef} className="h-px list-none" aria-hidden />
      </ul>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 text-sm text-ink-2">
          <button
            className="ui-btn-ghost px-3 py-1.5"
            disabled={currentPage <= 1}
            onClick={() => setPage(Math.max(1, currentPage - 1))}
          >
            {t('prevPage')}
          </button>
          <input
            key={currentPage}
            className="ui-input w-14 px-2 py-1 text-center text-sm"
            defaultValue={currentPage}
            inputMode="numeric"
            aria-label={tf('pageOf', { x: currentPage, n: totalPages })}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                jumpToPage(e.currentTarget.value)
                e.currentTarget.blur()
              }
            }}
            onBlur={(e) => {
              e.target.value = String(currentPage)
            }}
          />
          <span>{tf('pageOf', { x: currentPage, n: totalPages })}</span>
          <button
            className="ui-btn-ghost px-3 py-1.5"
            disabled={currentPage >= totalPages}
            onClick={() => setPage(Math.min(totalPages, currentPage + 1))}
          >
            {t('nextPage')}
          </button>
        </div>
      )}

      {renameTarget && (
        <div className="ui-modal-mask fixed inset-0 z-10 flex items-center justify-center p-4">
          <form
            className="ui-card ui-modal w-full max-w-sm p-6"
            onSubmit={handleRenameSubmit}
          >
            <h3 className="text-sm font-bold text-ink">{t('renameDialogTitle')}</h3>
            <input
              className="ui-input mt-3 w-full px-3 py-2 text-sm"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              placeholder={t('renamePlaceholder')}
              autoFocus
            />
            <div className="mt-3 flex items-center gap-4 text-sm text-ink-2">
              <span className="text-xs text-ink-3">{t('renameLangLabel')}</span>
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
            {renameError && <p className="mt-2 text-sm text-danger">{renameError}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                className="ui-btn-ghost px-3 py-1.5 text-sm"
                onClick={() => setRenameTarget(null)}
                disabled={renameSubmitting}
              >
                {t('cancel')}
              </button>
              <button
                type="submit"
                className="ui-btn-primary px-3 py-1.5 text-sm"
                disabled={renameSubmitting || !renameValue.trim()}
              >
                {renameSubmitting ? t('renaming') : t('confirm')}
              </button>
            </div>
          </form>
        </div>
      )}

      {deletingItem && (
        <div className="ui-modal-mask fixed inset-0 z-50 flex items-center justify-center">
          <div className="ui-card ui-modal w-full max-w-sm p-5">
            <h3 className="text-sm font-bold text-ink">{t('deleteCascadeTitle')}</h3>
            <p className="mt-2 text-sm text-ink-2">{t('deleteCascadeBody')}</p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="ui-btn-ghost px-3 py-1.5 text-sm"
                onClick={() => setDeletingItem(null)}
              >
                {t('cancel')}
              </button>
              <button
                className="ui-btn-danger px-3 py-1.5 text-sm"
                onClick={handleConfirmDelete}
              >
                {t('deleteAnyway')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
