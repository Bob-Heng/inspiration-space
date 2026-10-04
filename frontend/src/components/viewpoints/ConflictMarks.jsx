// 冲突标记：观点编号下方逐行列出冲突对方（四芒星 + 红色对方编号）。
// conflict_with 为后端换算好的展示编号；为空不渲染。
export default function ConflictMarks({ conflictWith }) {
  if (!conflictWith?.length) return null
  return (
    <span className="mt-0.5 flex flex-col gap-0.5">
      {conflictWith.map((n) => (
        <span key={n} className="flex items-center gap-1 text-xs leading-none">
          <svg
            viewBox="0 0 10 10"
            aria-hidden
            className="h-2.5 w-2.5 shrink-0 fill-danger stroke-ink"
            strokeWidth="1"
            strokeLinejoin="round"
          >
            <path d="M5 0 L6.2 3.8 L10 5 L6.2 6.2 L5 10 L3.8 6.2 L0 5 L3.8 3.8 Z" />
          </svg>
          <span className="font-mono text-danger">{n}</span>
        </span>
      ))}
    </span>
  )
}
