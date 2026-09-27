import { RELATION_LABELS } from '../../vocab'

function Section({ title, children }) {
  return (
    <section>
      <h3 className="text-xs font-bold text-slate-500">{title}</h3>
      <div className="mt-1 text-sm text-slate-800">{children}</div>
    </section>
  )
}

export default function AnalysisCard({ analysis, loading, onAnalyze }) {
  const tags = analysis?.tags ?? {}

  return (
    <div className="rounded-lg bg-white p-4 shadow">
      <div className="flex items-center">
        <h2 className="text-sm font-bold text-slate-800">AI 分析</h2>
        <button
          className="ml-auto rounded bg-slate-800 px-3 py-1.5 text-sm text-white hover:bg-slate-700 disabled:opacity-50"
          onClick={onAnalyze}
          disabled={loading}
        >
          {loading ? '生成中…' : analysis ? '重新生成' : '生成分析'}
        </button>
      </div>

      {loading && <p className="mt-3 text-sm text-slate-400">正在分析，请稍候…</p>}
      {!analysis && !loading && (
        <p className="mt-3 text-sm text-slate-400">
          点击「生成分析」，AI 将给出采纳理由、反对理由、分层与标签建议。
        </p>
      )}

      {analysis && (
        <div className="mt-3 space-y-4">
          <Section title="采纳理由">
            <p className="whitespace-pre-wrap">{analysis.adoption_reason}</p>
          </Section>
          <Section title="最强反对理由">
            <p className="whitespace-pre-wrap">{analysis.strongest_counterargument}</p>
          </Section>
          <Section title="分层建议">
            <p>{analysis.layer ?? '无'}</p>
          </Section>
          <Section title="标签建议">
            <ul className="grid grid-cols-2 gap-x-4 gap-y-1">
              <li>领域：{tags.domain ?? '无'}</li>
              <li>圈层：{tags.circle ?? '无'}</li>
              <li>学科：{tags.discipline ?? '无'}</li>
              <li>场景：{tags.scene ?? '无'}</li>
            </ul>
          </Section>
          <Section title="相近 / 冲突关系">
            {analysis.relations?.length ? (
              <ul className="space-y-1">
                {analysis.relations.map((rel) => (
                  <li key={`${rel.type}-${rel.viewpoint_id}`}>
                    <span
                      className={`mr-1 rounded px-1.5 py-0.5 text-xs ${
                        rel.type === 'conflict'
                          ? 'bg-red-100 text-red-700'
                          : 'bg-slate-200 text-slate-600'
                      }`}
                    >
                      {RELATION_LABELS[rel.type] ?? rel.type}
                    </span>
                    观点 #{rel.viewpoint_id}
                  </li>
                ))}
              </ul>
            ) : (
              <p>无</p>
            )}
          </Section>
          <Section title="AI 第一轮疑问">
            {analysis.questions?.length ? (
              <ol className="list-decimal space-y-1 pl-5">
                {analysis.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ol>
            ) : (
              <p>无</p>
            )}
          </Section>
        </div>
      )}
    </div>
  )
}
