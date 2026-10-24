function isOpeningCall(toolCall) {
  return Number(toolCall.turn_id) === 0
}

export function buildDiscussionTimeline(messages = [], toolCalls = []) {
  const entries = toolCalls.map((toolCall, index) => ({ toolCall, index }))
  const placed = new Set()
  const items = []
  const seenAssistantPhases = new Set()
  let seenAssistant = false

  function placeCall(entry) {
    placed.add(entry.index)
    items.push({
      type: 'tool',
      key: `tool-${entry.toolCall.call_id}`,
      toolCall: entry.toolCall,
    })
  }

  for (const message of messages) {
    if (message.role === 'assistant') {
      for (const entry of entries) {
        if (placed.has(entry.index) || !isOpeningCall(entry.toolCall)) continue
        const callPhase = entry.toolCall.phase
        const messagePhase = message.phase
        const phaseMatches =
          callPhase && messagePhase
            ? callPhase === messagePhase
            : !seenAssistant
        const phaseSeen =
          callPhase && messagePhase
            ? seenAssistantPhases.has(callPhase)
            : seenAssistant
        if (phaseMatches && !phaseSeen) placeCall(entry)
      }
      if (message.phase) seenAssistantPhases.add(message.phase)
      seenAssistant = true
    }

    items.push({ type: 'message', key: `message-${message.id}`, message })

    if (message.role === 'user') {
      for (const entry of entries) {
        if (placed.has(entry.index) || isOpeningCall(entry.toolCall)) continue
        if (String(entry.toolCall.turn_id) === String(message.id)) placeCall(entry)
      }
    }
  }

  for (const entry of entries) {
    if (!placed.has(entry.index)) placeCall(entry)
  }
  return items
}
