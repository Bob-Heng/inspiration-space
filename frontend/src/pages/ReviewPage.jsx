import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import ScrollElevator from '../components/ScrollElevator'
import { api } from '../api'
import AnalysisCard from '../components/review/AnalysisCard'
import DecisionBar from '../components/review/DecisionBar'
import DiscussionCard from '../components/review/DiscussionCard'
import { PolishEntryModal, PolishReadyModal } from '../components/review/PhaseModals'
import RelationsPanel from '../components/review/RelationsPanel'
import ReviewQueue from '../components/review/ReviewQueue'
import ItemTitle from '../components/ItemTitle'
import TranslatedText from '../components/TranslatedText'
import { usePageHeader } from '../header'
import { LangSelect, useLang } from '../i18n'

export default function ReviewPage() {
  const { t, tf, lang } = useLang()
  const [searchParams, setSearchParams] = useSearchParams()
  const headerItems = useMemo(
    () => [{ hk: 'lang', node: <LangSelect /> }],
    [],
  )
  usePageHeader({
    current: 'review',
    subtitle: t('reviewWorkbench'),
    slogan: t('reviewSlogan'),
    items: headerItems,
  })
  const [queue, setQueue] = useState([])
  const [queueError, setQueueError] = useState(null)
  const [session, setSession] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [analysisEn, setAnalysisEn] = useState(null)
  const [related, setRelated] = useState([])
  const [sessionLoading, setSessionLoading] = useState(false)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  // 两阶段：phaseModal 控制进入/收敛弹窗；distillSignal 保存最近一次提炼信号；
  // polishBusy 覆盖 enter-polish 调用期（分析生成期复用 analysisLoading 防重复提交）
  const [phaseModal, setPhaseModal] = useState(null) // null | 'entry' | 'ready'
  const [phaseError, setPhaseError] = useState(null)
  const [distillSignal, setDistillSignal] = useState(null)
  const [polishBusy, setPolishBusy] = useState(false)
  const attemptedRef = useRef(null)
  const queueAsideRef = useRef(null)

  const phase = session?.phase ?? 'polish'

  // 待打磨队列 = draft 观点列表（id 为观点 id，title_* 为关联灵感标题，仅作工作名）
  const loadQueue = useCallback(async () => {
    try {
      const items = await api.getReviewQueue()
      setQueue([...items].sort((a, b) => a.id - b.id))
      setQueueError(null)
    } catch (err) {
      setQueueError(err.message)
    }
  }, [])

  useEffect(() => {
    loadQueue()
  }, [loadQueue])

  // targetSession：弹窗确认进入打磨时传入已转阶段的会话（此时 session 状态尚未生效）；
  // 打磨形态手动点击"生成分析"时不传，回退到当前 session 状态
  const handleAnalyze = useCallback(async (targetSession = null) => {
    const current = targetSession ?? session
    if (!current || analysisLoading) return
    // 已有分析即为重新生成：后端会先清空打磨阶段对话（提炼对话保留），需二次确认
    const regen = Boolean(current.analysis ?? analysis)
    if (regen && !window.confirm(t('regenerateConfirm'))) return
    setAnalysisLoading(true)
    setError(null)
    try {
      const result = await api.analyzeViewpoint(current.viewpoint_id, regen)
      // 分析接口只回原文；英文版随会话持久化，回拉活动会话取 analysis_en（失败则用原文）。
      // 重新生成时后端已清空打磨对话，会话体一并回拉替换，保持消息与分析一致
      const fresh = await api.getActiveSession().catch(() => null)
      const related = await fetchRelations(result.relations)
      // 原子落地：分析/英译/关联观点同帧出现，避免分栏陆续蹦出
      setAnalysis(result)
      setAnalysisEn(fresh?.analysis_en ?? null)
      setRelated(related)
      if (regen && fresh) setSession(fresh)
      // 分析落库后刷新队列（观点正文可能已随草稿更新）
      await loadQueue()
      if (regen) {
        // 打磨讨论已被后端清空：请 AI 重发"进入打磨"的衔接首问
        try {
          const opening = await api.postOpeningQuestion(current.id, false, true)
          if (opening) {
            setSession((s) =>
              s ? { ...s, messages: [...s.messages, opening] } : s,
            )
          }
        } catch {
          // 衔接首问失败不阻断：用户可直接发言继续打磨讨论
        }
      } else if (!current.messages?.some((m) => m.role === 'user')) {
        // 分析完成后刷新 AI 首问：用户未发言时，旧首问作废、按新分析重提
        try {
          const opening = await api.postOpeningQuestion(current.id, true)
          if (opening) {
            setSession((s) => ({ ...s, messages: [opening] }))
          }
        } catch {
          // 首问失败不阻断分析展示，用户可自行发言开启讨论
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setAnalysisLoading(false)
    }
  }, [session, analysis, analysisLoading, loadQueue, t])

  const openSession = useCallback(async (viewpointId) => {
    setSessionLoading(true)
    setError(null)
    setNotice(null)
    setPhaseModal(null)
    setPhaseError(null)
    setDistillSignal(null)
    try {
      const s = await api.startReviewSession(viewpointId)
      // 全套展示数据拉齐后一次性落地（含关联观点），所有栏同帧出现
      const bundle = await fetchSessionBundle(s)
      applyBundle(s, bundle)
      // 全新的提炼会话（phase=distill 且无消息无分析）：先做观点判断——会话内
      // is_viewpoint 为 true 直接弹进入弹窗（暂不生成分析）；null 调 live 判断
      // 按结果走；false 留在提炼形态并请 AI 首问；判断失败走页面错误条、留在
      // 提炼形态。已进入打磨但尚未生成分析的会话不是新会话，跳过判断直接进打磨形态。
      if (s.phase === 'distill' && !s.analysis && (s.messages?.length ?? 0) === 0) {
        try {
          let isViewpoint = s.viewpoint?.is_viewpoint
          if (isViewpoint == null) {
            const check = await api.checkViewpoint(s.id)
            isViewpoint = check?.is_viewpoint ?? false
          }
          if (isViewpoint) {
            setPhaseModal('entry')
          } else {
            await maybeRequestOpening(s)
          }
        } catch (checkErr) {
          setError(checkErr.message)
          await maybeRequestOpening(s)
        }
      } else {
        await maybeRequestOpening(s)
      }
    } catch (err) {
      setSession(null)
      setAnalysis(null)
      setAnalysisEn(null)
      setRelated([])
      setError(err.message)
    } finally {
      setSessionLoading(false)
    }
  }, [])

  // 拉取关联观点（不落地）；分析/英译随会话体直接取
  async function fetchRelations(relations) {
    if (!relations?.length) return []
    return Promise.all(
      relations.map(async (relation) => {
        try {
          const viewpoint = await api.getViewpoint(relation.viewpoint_id)
          return { relation, viewpoint }
        } catch {
          return { relation, viewpoint: null }
        }
      }),
    )
  }

  async function fetchSessionBundle(s) {
    return {
      analysis: s.analysis ?? null,
      analysisEn: s.analysis_en ?? null,
      related: await fetchRelations(s.analysis?.relations),
    }
  }

  // 会话 + 分析 + 英译 + 关联观点：同一次同步块内全部落地（React 批处理为一帧）
  function applyBundle(s, bundle) {
    setSession(s)
    setAnalysis(bundle.analysis)
    setAnalysisEn(bundle.analysisEn)
    setRelated(bundle.related)
  }

  // AI 首问：还没有讨论消息，且（已有分析 或 处于提炼阶段）时，请 AI 主动开问
  async function maybeRequestOpening(s) {
    if ((s?.messages?.length ?? 0) > 0) return
    if (!s?.analysis && (s?.phase ?? 'polish') !== 'distill') return
    try {
      const opening = await api.postOpeningQuestion(s.id)
      if (opening) {
        setSession((cur) =>
          cur && cur.id === s.id
            ? { ...cur, messages: [...cur.messages, opening] }
            : cur,
        )
      }
    } catch {
      // 首问失败静默：用户可自行发言开启讨论
    }
  }

  // 进入审议页时自动恢复未完成的会话（关窗重开保留现场）。
  // URL 已带明确 viewpoint 参数时跳过恢复：显式选择优先，
  // 防止恢复的异步结果被"开始打磨/队列点击"的显式会话覆盖（竞态踩回旧会话）。
  useEffect(() => {
    if (session) return
    if (searchParams.get('viewpoint')) return
    setSessionLoading(true)
    api
      .getActiveSession()
      .then(async (s) => {
        if (!s) return
        // 等待期间用户已做了显式选择（点了队列条目或带着参数进来）：不覆盖
        if (attemptedRef.current != null && attemptedRef.current !== s.viewpoint_id) {
          return
        }
        // 全套展示数据拉齐后一次性落地（含关联观点），所有栏同帧出现
        const bundle = await fetchSessionBundle(s)
        applyBundle(s, bundle)
        setSearchParams({ viewpoint: String(s.viewpoint_id) })
        attemptedRef.current = s.viewpoint_id
        await maybeRequestOpening(s)
      })
      .catch(() => {})
      .finally(() => setSessionLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const id = Number(searchParams.get('viewpoint'))
    if (!id) return
    if (session?.viewpoint_id === id) return
    if (attemptedRef.current === id) return
    attemptedRef.current = id
    openSession(id)
  }, [searchParams, session, openSession])

  function handleSelect(viewpointId) {
    attemptedRef.current = null
    setSearchParams({ viewpoint: String(viewpointId) })
  }

  async function handleSend(content) {
    if (!session || sending) return false
    setSending(true)
    setError(null)
    try {
      const { user_message, assistant_message, distill_signal } =
        await api.sendReviewMessage(session.id, {
          content,
          analysis: analysis ?? undefined,
        })
      // 收敛轮 assistant_message 为 null：回复被弹窗接管，不进对话框
      setSession((s) => ({
        ...s,
        messages: [
          ...s.messages,
          user_message,
          ...(assistant_message ? [assistant_message] : []),
        ],
      }))
      // 提炼信号（仅 distill 阶段非空）：保存最近一次；AI 判定收敛时弹收敛弹窗
      if (distill_signal) {
        setDistillSignal(distill_signal)
        if (distill_signal.ready_to_polish && phase === 'distill') {
          setPhaseError(null)
          setPhaseModal('ready')
        }
      }
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setSending(false)
    }
  }

  // 进入/收敛弹窗确认：存档草稿并转打磨阶段，然后以草稿为对象生成 AI 分析，
  // 最后请 AI 发"进入打磨"的衔接首问（提炼讨论保留，打磨讨论由此接续）；
  // 弹窗在 enter-polish 与分析生成期间保持打开并 loading，防止重复提交
  async function confirmEnterPolish(draft) {
    if (!session || polishBusy || analysisLoading) return
    setPolishBusy(true)
    setPhaseError(null)
    try {
      const updated = await api.enterPolish(session.id, draft)
      setSession(updated)
      setDistillSignal(null)
      await handleAnalyze(updated)
      setPhaseModal(null)
      try {
        const opening = await api.postOpeningQuestion(updated.id, false, true)
        if (opening) {
          setSession((s) =>
            s && s.id === updated.id
              ? { ...s, messages: [...s.messages, opening] }
              : s,
          )
        }
      } catch {
        // 衔接首问失败不阻断：用户可直接发言继续打磨讨论
      }
      // 阶段已转打磨：刷新队列阶段徽标（handleAnalyze 成功时内部也刷，这里兜底其失败路径）
      await loadQueue()
    } catch (err) {
      setPhaseError(err.message)
    } finally {
      setPolishBusy(false)
    }
  }

  // 进入弹窗"继续提炼"：留在提炼形态，请 AI 首问开启讨论
  async function stayDistilling() {
    setPhaseModal(null)
    if (session) await maybeRequestOpening(session)
  }

  // 收敛弹窗"继续讨论"：被压下的 AI 回复临时补进对话框保持连贯
  // （该回复未落库——刷新后不再出现，AI 下一轮也看不到它）
  function stayDiscussing() {
    setPhaseModal(null)
    if (!distillSignal?.reply) return
    const localReply = {
      id: `local-${Date.now()}`,
      role: 'assistant',
      content: distillSignal.reply,
      content_zh: distillSignal.reply,
      content_en: null,
      original_lang: 'zh',
      created_at: new Date().toISOString(),
    }
    setSession((s) => (s ? { ...s, messages: [...s.messages, localReply] } : s))
  }

  // 撤销/阶段回退统一落地：后端返回完整会话（undo-phase 后分析与打磨消息已清），
  // 提炼信号随之作废（对应消息可能已被撤销）
  async function applyUpdatedSession(updated) {
    setSession(updated)
    setAnalysis(updated.analysis ?? null)
    setAnalysisEn(updated.analysis_en ?? null)
    setRelated(await fetchRelations(updated.analysis?.relations))
    setDistillSignal(null)
  }

  // 消息级撤销：删当前阶段最后一条消息
  async function handleUndo() {
    if (!session) return
    setError(null)
    try {
      await applyUpdatedSession(await api.undoReviewSession(session.id))
    } catch (err) {
      setError(err.message)
    }
  }

  // 阶段级回退（长按触发，DecisionBar 内已 confirm）：polish→distill / distill→重置
  async function handleUndoPhase() {
    if (!session) return
    setError(null)
    try {
      await applyUpdatedSession(await api.undoReviewPhase(session.id))
      setPhaseModal(null)
      setPhaseError(null)
      // 阶段可能已回退到提炼：刷新队列阶段徽标
      await loadQueue()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDecision(payload) {
    const result = await api.submitReviewDecision(session.id, payload)
    const template = t('decisionDone').accept
    setNotice(
      template.replaceAll('{id}', String(result.display_id ?? result.viewpoint_id ?? '')),
    )
    // 保持 attemptedRef 为已采纳观点 id：防止清空会话的瞬间旧 URL 参数
    // 触发对该观点的二次开会话（后端返回"已打磨完成，不得再次打磨"）
    attemptedRef.current = session.viewpoint_id
    setSession(null)
    setAnalysis(null)
    setAnalysisEn(null)
    setRelated([])
    setPhaseModal(null)
    setPhaseError(null)
    setDistillSignal(null)
    setSearchParams({})
    await loadQueue()
  }

  // 展示用分析：英文界面且会话带英文版时替换文本字段；layer/tags 为数据值沿用原对象
  const displayAnalysis =
    lang === 'en' && analysis && analysisEn
      ? {
          ...analysis,
          adoption_reason: analysisEn.adoption_reason ?? analysis.adoption_reason,
          strongest_counterargument:
            analysisEn.strongest_counterargument ?? analysis.strongest_counterargument,
          questions: analysisEn.questions ?? analysis.questions,
        }
      : analysis

  return (
    <div className="flex min-h-screen flex-col bg-paper pb-20 lg:h-screen lg:overflow-hidden lg:pb-20">
      <main className="ui-reveal mx-auto flex min-h-0 w-full max-w-7xl flex-1 flex-col px-4 py-6 lg:overflow-hidden">
        {notice && (
          <div className="mb-4 shrink-0 rounded-lg bg-accent-soft px-4 py-3 text-sm text-accent">
            {notice}
          </div>
        )}
        {error && (
          <div className="mb-4 shrink-0 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger">
            {error}
          </div>
        )}

        {/* 三栏各自独立滚动：栏位固定，内容在栏内滚动，互不影响 */}
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-12 lg:overflow-hidden">
          <aside
            ref={queueAsideRef}
            className="min-h-0 lg:col-span-3 lg:h-full lg:overflow-y-auto lg:pr-1"
          >
            <ReviewQueue
              items={queue}
              selectedId={session?.viewpoint_id ?? null}
              onSelect={handleSelect}
              error={queueError}
            />
            <div className="sticky bottom-2 mt-2 flex justify-end">
              <ScrollElevator target={queueAsideRef} inline />
            </div>
          </aside>

          <section
            className={`min-h-0 space-y-4 lg:h-full lg:overflow-y-auto lg:pr-1 ${
              phase === 'distill' ? 'lg:col-span-9' : 'lg:col-span-6'
            }`}
          >
            {session ? (
              <>
                <div className="ui-card p-4">
                  <div className="flex items-center gap-3 text-xs text-ink-2">
                    <span className="font-mono text-accent">
                      #{session.viewpoint.source_inspiration_id ?? session.viewpoint.id}
                    </span>
                    <span>
                      {tf('sourceDate', {
                        date: session.viewpoint.source_date ?? t('noSourceDate'),
                      })}
                    </span>
                  </div>
                  <ItemTitle
                    titleZh={session.viewpoint.title_zh}
                    titleEn={session.viewpoint.title_en}
                    id={session.viewpoint.id}
                  />
                  <p className="mt-2 whitespace-pre-wrap text-ink">
                    <TranslatedText
                      contentZh={session.viewpoint.content_zh}
                      contentEn={session.viewpoint.content_en}
                      originalLang={session.viewpoint.original_lang}
                    />
                  </p>
                </div>
                {phase === 'polish' && (
                  <AnalysisCard
                    analysis={displayAnalysis}
                    loading={analysisLoading}
                    onAnalyze={() => handleAnalyze()}
                  />
                )}
                <DiscussionCard
                  session={session}
                  sending={sending}
                  onSend={handleSend}
                  phase={phase}
                  onEnterPolish={() => {
                    setPhaseError(null)
                    setPhaseModal('ready')
                  }}
                />
              </>
            ) : (
              <div className="ui-card p-10 text-center text-sm text-ink-3">
                {sessionLoading ? t('creatingSession') : t('pickInspiration')}
              </div>
            )}
          </section>

          {phase === 'polish' && (
            <aside className="min-h-0 lg:col-span-3 lg:h-full lg:overflow-y-auto lg:pr-1">
              <RelationsPanel analysis={analysis} related={related} />
            </aside>
          )}
        </div>
      </main>


      <DecisionBar
        key={session?.id ?? 'none'}
        phase={phase}
        session={session}
        analysis={analysis}
        related={related}
        onSubmit={handleDecision}
        onUndo={handleUndo}
        onUndoPhase={handleUndoPhase}
      />

      {phaseModal === 'entry' && (
        <PolishEntryModal
          busy={polishBusy || analysisLoading}
          error={phaseError}
          onConfirm={() => confirmEnterPolish(null)}
          onStay={stayDistilling}
        />
      )}
      {phaseModal === 'ready' && (
        <PolishReadyModal
          busy={polishBusy || analysisLoading}
          error={phaseError}
          initialDraft={
            distillSignal?.distilled_viewpoint ||
            session?.viewpoint?.content ||
            ''
          }
          onConfirm={confirmEnterPolish}
          onStay={stayDiscussing}
        />
      )}
    </div>
  )
}
