export function handleTextareaEnter(event, onSubmit) {
  if (event.key !== 'Enter' || event.nativeEvent.isComposing) return
  event.preventDefault()
  if (event.ctrlKey) {
    const textarea = event.currentTarget
    const { selectionStart, selectionEnd, value } = textarea
    textarea.value = `${value.slice(0, selectionStart)}\n${value.slice(selectionEnd)}`
    textarea.selectionStart = textarea.selectionEnd = selectionStart + 1
    textarea.dispatchEvent(new Event('input', { bubbles: true }))
    return
  }
  onSubmit(event)
}
