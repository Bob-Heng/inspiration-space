import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import ScrollElevator from '../components/ScrollElevator'
import { api } from '../api'
import AnalysisCard from '../components/review/AnalysisCard'
import DecisionBar from '../components/review/DecisionBar'
import DiscussionCard from '../components/review/DiscussionCard'
import RelationsPanel from '../components/review/RelationsPanel'
import ReviewQueue from '../components/review/ReviewQueue'
import ItemTitle from '../components/ItemTitle'
import TranslatedText from '../components/TranslatedText'
import { useLang } from '../i18n'

export default function ReviewPage() {
  const { t, tf, lang } = useLang()
  const [searchParams, setSearchParams] = useSearchParams()
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
  const attemptedRef = useRef(null)
  const queueAsideRef = useRef(null)

  const loadQueue = useCallback(async () => {
    try {
      const [pending, inReview] = await Promise.all([
        api.listInspirations({ status: 'pending' }),
        api.listInspirations({ status: 'in_review' }),
      ])
      setQueue([...pending, ...inReview].sort((a, b) => a.id - b.id))
      setQueueError(null)
    } catch (err) {
      setQueueError(err.message)
    }
  }, [])

  useEffect(() => {
    loadQueue()
  }, [loadQueue])

  const openSession = useCallback(async (inspirationId) => {
    setSessionLoading(true)
    setError(null)
    setNotice(null)
    try {
      const s = await api.startReviewSession(inspirationId)
      setSession(s)
      await restoreAnalysis(s.analysis ?? null, s.analysis_en ?? null)
      await maybeRequestOpening(s)
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

  // 恢复/展示一次分析结果（含右侧关联观点的加载）；resultEn 为会话伴生的英文版
  async function restoreAnalysis(result, resultEn = null) {
    setAnalysis(result)
    setAnalysisEn(resultEn)
    if (!result?.relations?.length) {
      setRelated([])
      return
    }
    const fetched = await Promise.all(
      result.relations.map(async (relation) => {
        try {
          const viewpoint = await api.getViewpoint(relation.viewpoint_id)
          return { relation, viewpoint }
        } catch {
          return { relation, viewpoint: null }
        }
      }),
    )
    setRelated(fetched)
  }

  // AI 首问：会话已有分析但还没有讨论消息时，请 AI 主动开问
  async function maybeRequestOpening(s) {
    if (!s?.analysis || (s.messages?.length ?? 0) > 0) return
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

  // 进入审议页时自动恢复未完成的会话（关窗重开保留现场）
  useEffect(() => {
    if (session) return
    api
      .getActiveSession()
      .then(async (s) => {
        if (s) {
          setSession(s)
          setSearchParams({ inspiration: String(s.inspiration_id) })
          attemptedRef.current = s.inspiration_id
          await restoreAnalysis(s.analysis ?? null, s.analysis_en ?? null)
          await maybeRequestOpening(s)
        }
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const id = Number(searchParams.get('inspiration'))
    if (!id) return
    if (session?.inspiration_id === id) return
    if (attemptedRef.current === id) return
    attemptedRef.current = id
    openSession(id)
  }, [searchParams, session, openSession])

  function handleSelect(inspirationId) {
    attemptedRef.current = null
    setSearchParams({ inspiration: String(inspirationId) })
  }

  async function handleAnalyze() {
    if (!session || analysisLoading) return
    setAnalysisLoading(true)
    setError(null)
    try {
      const result = await api.analyzeInspiration(session.inspiration_id)
      setAnalysis(result)
      // 分析接口只回原文；英文版随会话持久化，回拉活动会话取 analysis_en（失败则用原文）
      const fresh = await api.getActiveSession().catch(() => null)
      setAnalysisEn(fresh?.analysis_en ?? null)
      const fetched = await Promise.all(
        (result.relations ?? []).map(async (relation) => {
          try {
            const viewpoint = await api.getViewpoint(relation.viewpoint_id)
            return { relation, viewpoint }
          } catch {
            return { relation, viewpoint: null }
          }
        }),
      )
      setRelated(fetched)
      // 分析完成后刷新 AI 首问：用户未发言时，旧首问作废、按新分析重提
      if (!session?.messages?.some((m) => m.role === 'user')) {
        try {
          const opening = await api.postOpeningQuestion(session.id, true)
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
  }

  async function handleSend(content) {
    if (!session || sending) return false
    setSending(true)
    setError(null)
    try {
      const { user_message, assistant_message } = await api.sendReviewMessage(
        session.id,
        { content, analysis: analysis ?? undefined },
      )
      setSession((s) => ({
        ...s,
        messages: [...s.messages, user_message, assistant_message],
      }))
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setSending(false)
    }
  }

  async function handleDecision(payload) {
    const result = await api.submitReviewDecision(session.id, payload)
    const template = t('decisionDone')[result.decision_type]
    setNotice(
      template
        ? template.replaceAll('{id}', String(result.display_id ?? result.viewpoint_id ?? ''))
        : t('decisionSubmitted'),
    )
    // 保持 attemptedRef 为已审议灵感 id：防止清空会话的瞬间旧 URL 参数
    // 触发对该灵感的二次开会话（后端返回"已审议完成，不得再次审议"）
    attemptedRef.current = session.inspiration_id
    setSession(null)
    setAnalysis(null)
    setAnalysisEn(null)
    setRelated([])
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
    <div className="flex min-h-screen flex-col bg-slate-50 pb-20 lg:h-screen lg:overflow-hidden lg:pb-20">
      <PageHeader current="review" subtitle={t('reviewWorkbench')} />

      <main className="mx-auto flex min-h-0 w-full max-w-7xl flex-1 flex-col px-4 py-6 lg:overflow-hidden">
        {notice && (
          <div className="mb-4 shrink-0 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {notice}
          </div>
        )}
        {error && (
          <div className="mb-4 shrink-0 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
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
              selectedId={session?.inspiration_id ?? null}
              onSelect={handleSelect}
              error={queueError}
            />
            <div className="sticky bottom-2 mt-2 flex justify-end">
              <ScrollElevator target={queueAsideRef} inline />
            </div>
          </aside>

          <section className="min-h-0 space-y-4 lg:col-span-6 lg:h-full lg:overflow-y-auto lg:pr-1">
            {session ? (
              <>
                <div className="rounded-lg bg-white p-4 shadow">
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span className="font-mono">#{session.inspiration.id}</span>
                    <span>
                      {tf('sourceDate', {
                        date: session.inspiration.source_date ?? t('noSourceDate'),
                      })}
                    </span>
                  </div>
                  <ItemTitle
                    titleZh={session.inspiration.title_zh}
                    titleEn={session.inspiration.title_en}
                    id={session.inspiration.id}
                  />
                  <p className="mt-2 whitespace-pre-wrap text-slate-800">
                    <TranslatedText
                      contentZh={session.inspiration.content_zh}
                      contentEn={session.inspiration.content_en}
                      originalLang={session.inspiration.original_lang}
                    />
                  </p>
                </div>
                <AnalysisCard
                  analysis={displayAnalysis}
                  loading={analysisLoading}
                  onAnalyze={handleAnalyze}
                />
                <DiscussionCard
                  session={session}
                  sending={sending}
                  onSend={handleSend}
                />
              </>
            ) : (
              <div className="rounded-lg bg-white p-10 text-center text-sm text-slate-400 shadow">
                {sessionLoading ? t('creatingSession') : t('pickInspiration')}
              </div>
            )}
          </section>

          <aside className="min-h-0 lg:col-span-3 lg:h-full lg:overflow-y-auto lg:pr-1">
            <RelationsPanel analysis={analysis} related={related} />
          </aside>
        </div>
      </main>


      <DecisionBar
        key={session?.id ?? 'none'}
        session={session}
        analysis={analysis}
        related={related}
        onSubmit={handleDecision}
      />
    </div>
  )
}
