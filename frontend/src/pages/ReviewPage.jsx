import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import AnalysisCard from '../components/review/AnalysisCard'
import DecisionBar from '../components/review/DecisionBar'
import DiscussionCard from '../components/review/DiscussionCard'
import RelationsPanel from '../components/review/RelationsPanel'
import ReviewQueue from '../components/review/ReviewQueue'

const DECISION_NOTICES = {
  accept: (r) => `已采纳，观点 #${r.viewpoint_id} 已入库`,
  accept_modified: (r) => `已采纳（修改后），观点 #${r.viewpoint_id} 已入库`,
  reject: () => '已否定，该灵感已标记为已否定',
  defer: () => '已暂缓，灵感回到待审队列',
}

export default function ReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [queue, setQueue] = useState([])
  const [queueError, setQueueError] = useState(null)
  const [session, setSession] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [related, setRelated] = useState([])
  const [sessionLoading, setSessionLoading] = useState(false)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const attemptedRef = useRef(null)

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
      await restoreAnalysis(s.analysis ?? null)
    } catch (err) {
      setSession(null)
      setAnalysis(null)
      setRelated([])
      setError(err.message)
    } finally {
      setSessionLoading(false)
    }
  }, [])

  // 恢复/展示一次分析结果（含右侧关联观点的加载）
  async function restoreAnalysis(result) {
    setAnalysis(result)
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

  // 进入审议页时自动恢复未完成的会话（关窗重开保留现场）
  useEffect(() => {
    if (session) return
    api
      .getActiveSession()
      .then((s) => {
        if (s) {
          setSession(s)
          setSearchParams({ inspiration: String(s.inspiration_id) })
          attemptedRef.current = s.inspiration_id
          return restoreAnalysis(s.analysis ?? null)
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
    const make = DECISION_NOTICES[result.decision_type]
    setNotice(make ? make(result) : '决策已提交')
    // 保持 attemptedRef 为已审议灵感 id：防止清空会话的瞬间旧 URL 参数
    // 触发对该灵感的二次开会话（后端返回"已审议完成，不得再次审议"）
    attemptedRef.current = session.inspiration_id
    setSession(null)
    setAnalysis(null)
    setRelated([])
    setSearchParams({})
    await loadQueue()
  }

  return (
    <div className="min-h-screen bg-slate-50 pb-24">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center px-4 py-3">
          <h1 className="text-lg font-bold text-slate-800">审议工作台</h1>
          <div className="ml-auto flex items-center gap-4">
            <Link
              to="/viewpoints"
              className="text-sm text-slate-500 hover:text-slate-800"
            >
              观点库
            </Link>
            <Link to="/" className="text-sm text-slate-500 hover:text-slate-800">
              返回首页
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {notice && (
          <div className="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {notice}
          </div>
        )}
        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <aside className="lg:col-span-3">
            <ReviewQueue
              items={queue}
              selectedId={session?.inspiration_id ?? null}
              onSelect={handleSelect}
              error={queueError}
            />
          </aside>

          <section className="space-y-4 lg:col-span-6">
            {session ? (
              <>
                <div className="rounded-lg bg-white p-4 shadow">
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span className="font-mono">#{session.inspiration.id}</span>
                    <span>
                      来源日期：{session.inspiration.source_date ?? '无'}
                    </span>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-slate-800">
                    {session.inspiration.content}
                  </p>
                </div>
                <AnalysisCard
                  analysis={analysis}
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
                {sessionLoading
                  ? '正在建立审议会话…'
                  : '从左侧待审队列选择一条灵感，开始审议。'}
              </div>
            )}
          </section>

          <aside className="lg:col-span-3">
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
