import { useEffect, useRef, useState } from 'react'
import { useLang } from '../../i18n'

// 撤销键长按触发阶段级回退的时长
const LONG_PRESS_MS = 3000

// 底部栏：撤销（单击消息级 / 长按阶段级）。采纳不设手动按钮——
// 由 AI 判定打磨形成共识后弹出确认框完成（AdoptConfirmModal）。
export default function DecisionBar({ phase: phaseProp, session, onUndo, onUndoPhase }) {
  const { t, tf } = useLang()
  const [undoBusy, setUndoBusy] = useState(false)
  const pressTimerRef = useRef(null)
  const longPressFiredRef = useRef(false)

  // 阶段由父级传入（两阶段都渲染决策栏，均只保留撤销）
  const phase = phaseProp ?? session?.phase ?? 'polish'
  const active = session?.status === 'active'
  // 当前阶段消息数：消息带 phase 字段时按阶段过滤，不带则全部计入（由后端兜底拒空撤）
  const phaseMessageCount = (session?.messages ?? []).filter(
    (m) => !m.phase || m.phase === phase,
  ).length
  const undoDisabled = !session || !active || phaseMessageCount === 0 || undoBusy
  // 撤销地板：跳过提炼的观点（录入时已构成观点且无提炼消息），阶段回退无事可做，
  // 长按禁用（单击撤销本就限当前阶段，不受影响；后端 undo-phase 在此地板返回 409 兜底）
  const undoPhaseFloor =
    phase === 'polish' &&
    session?.viewpoint?.is_viewpoint === true &&
    !(session?.messages ?? []).some((m) => m.phase === 'distill')

  useEffect(
    () => () => {
      if (pressTimerRef.current) clearTimeout(pressTimerRef.current)
    },
    [],
  )

  // 单击撤销：长按已触发过时抑制本次单击
  async function handleUndoClick() {
    if (longPressFiredRef.current) {
      longPressFiredRef.current = false
      return
    }
    if (undoDisabled) return
    setUndoBusy(true)
    try {
      await onUndo()
    } finally {
      setUndoBusy(false)
    }
  }

  // 长按 3 秒：阶段级回退（pointerup/leave 取消计时）；撤销地板上长按禁用
  function handlePressStart() {
    if (undoDisabled || undoPhaseFloor) return
    longPressFiredRef.current = false
    pressTimerRef.current = setTimeout(() => {
      pressTimerRef.current = null
      longPressFiredRef.current = true
      const key =
        phase === 'polish' ? 'undoPhasePolishConfirm' : 'undoPhaseDistillConfirm'
      if (!window.confirm(t(key))) return
      setUndoBusy(true)
      Promise.resolve(onUndoPhase()).finally(() => setUndoBusy(false))
    }, LONG_PRESS_MS)
  }

  function handlePressCancel() {
    if (pressTimerRef.current) {
      clearTimeout(pressTimerRef.current)
      pressTimerRef.current = null
    }
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-10 border-t border-rule bg-white">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3">
        <span className="text-sm text-ink-2">
          {session
            ? tf('reviewingN', { id: session.viewpoint?.source_inspiration_id ?? session.viewpoint_id })
            : t('noInspirationSelected')}
        </span>
        <div className="ml-auto flex gap-2">
          <button
            className={`ui-btn-danger px-4 py-2 text-sm${undoPhaseFloor ? ' opacity-60' : ''}`}
            title={undoPhaseFloor ? t('undoFloorHint') : undefined}
            onPointerDown={handlePressStart}
            onPointerUp={handlePressCancel}
            onPointerLeave={handlePressCancel}
            onClick={handleUndoClick}
            disabled={undoDisabled}
          >
            {t('undo')}
          </button>
        </div>
      </div>
    </div>
  )
}
