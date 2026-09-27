import {
  LAYER_LABELS,
  RELATION_LABELS,
  VIEWPOINT_STATUS_LABELS,
  summarize,
} from '../../vocab'
import LlmSettingsCard from './LlmSettingsCard'

export default function RelationsPanel({ analysis, related }) {
  const tags = analysis?.tags ?? {}

  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-white p-4 shadow">
        <h2 className="text-sm font-bold text-slate-800">关联观点</h2>
        {!analysis ? (
          <p className="mt-2 text-sm text-slate-400">
            生成 AI 分析后，这里将展示相近 / 冲突观点。
          </p>
        ) : related.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">暂无关联观点。</p>
        ) : (
          <ul className="mt-3 space-y-2">
            {related.map(({ relation, viewpoint }) => (
              <li
                key={`${relation.type}-${relation.viewpoint_id}`}
                className="rounded border border-slate-200 p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-xs ${
                      relation.type === 'conflict'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-slate-200 text-slate-600'
                    }`}
                  >
                    {RELATION_LABELS[relation.type] ?? relation.type}
                  </span>
                  <span className="font-mono text-xs text-slate-400">
                    #{relation.viewpoint_id}
                  </span>
                </div>
                {viewpoint ? (
                  <>
                    <p className="mt-1 text-slate-800">
                      {summarize(viewpoint.content, 50)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      分层：{LAYER_LABELS[viewpoint.layer] ?? '无'} · 状态：
                      {VIEWPOINT_STATUS_LABELS[viewpoint.status] ?? viewpoint.status}
                    </p>
                  </>
                ) : (
                  <p className="mt-1 text-xs text-red-500">观点加载失败</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="rounded-lg bg-white p-4 shadow">
        <h2 className="text-sm font-bold text-slate-800">标签建议</h2>
        {!analysis ? (
          <p className="mt-2 text-sm text-slate-400">
            生成 AI 分析后，这里将展示分层与标签建议。
          </p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-slate-800">
            <li>分层：{analysis.layer ?? '无'}</li>
            <li>领域：{tags.domain ?? '无'}</li>
            <li>圈层：{tags.circle ?? '无'}</li>
            <li>学科：{tags.discipline ?? '无'}</li>
            <li>场景：{tags.scene ?? '无'}</li>
          </ul>
        )}
      </div>

      <LlmSettingsCard />
    </div>
  )
}
