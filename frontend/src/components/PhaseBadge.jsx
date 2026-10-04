import { useLang } from '../i18n'

// 阶段徽标（首页灵感列表与他山坊队列共用，保证两页一致）：
// 提炼=浅金、打磨=深金；金色仅小面积高光，符合 design.md 金色纪律
const PHASE_BADGES = {
  distill: 'bg-accent-2/25 text-ink-2',
  polish: 'bg-accent-2/70 text-ink',
}

export default function PhaseBadge({ phase, className = '' }) {
  const { t } = useLang()
  if (!PHASE_BADGES[phase]) return null
  return (
    <span
      className={`rounded-pill px-2 py-0.5 text-xs ${PHASE_BADGES[phase]} ${className}`}
    >
      {t(phase === 'distill' ? 'phaseDistill' : 'phasePolish')}
    </span>
  )
}
