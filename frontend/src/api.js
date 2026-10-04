// 开发模式（vite 5173）跨端口访问后端；打包后由后端同源托管，用相对路径
const BASE_URL = import.meta.env.DEV ? 'http://localhost:8000' : ''

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function request(path, options = {}) {
  const lang = localStorage.getItem('inspiration_lang') || 'zh'
  let res
  try {
    res = await fetch(BASE_URL + path, {
      credentials: 'include',
      ...options,
    })
  } catch {
    throw new ApiError(
      0,
      lang === 'en'
        ? 'Cannot reach the backend. Please make sure it is running (double-click 启动.bat).'
        : '无法连接后端，请确认后端已启动（可双击 启动.bat）',
    )
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    let detail = data?.detail
    // 双语错误：detail 为 { code, zh, en } 时按界面语言取值（api.js 不在组件树，直读 localStorage）
    if (detail && typeof detail === 'object') {
      detail = detail[lang] ?? detail.zh
    }
    throw new ApiError(
      res.status,
      detail ?? (lang === 'en' ? `Request failed (${res.status})` : `请求失败（${res.status}）`),
    )
  }
  return data
}

export const api = {
  login(username, password) {
    const body = new URLSearchParams({ username, password })
    return request('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    })
  },
  logout: () => request('/api/auth/logout', { method: 'POST' }),
  me: () => request('/api/auth/me'),
  authStatus: () => request('/api/auth/status'),
  setup(username, password, phone, birthday) {
    return request('/api/auth/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username,
        password,
        phone: phone || null,
        birthday: birthday || null,
      }),
    })
  },
  recover(method, value, newPassword) {
    return request('/api/auth/recover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method, value, new_password: newPassword }),
    })
  },

  listInspirations({ status, keyword } = {}) {
    const params = new URLSearchParams()
    if (status) params.set('status', status)
    if (keyword) params.set('keyword', keyword)
    const qs = params.toString()
    return request(`/api/inspirations${qs ? `?${qs}` : ''}`)
  },
  createInspiration(payload) {
    return request('/api/inspirations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  updateInspiration(id, payload) {
    return request(`/api/inspirations/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  deleteInspiration: (id) => request(`/api/inspirations/${id}`, { method: 'DELETE' }),
  renameTitle(id, title, lang) {
    return request(`/api/inspirations/${id}/rename-title`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, lang }),
    })
  },

  importDocxPreview(file) {
    const form = new FormData()
    form.append('file', file)
    return request('/api/inspirations/import', { method: 'POST', body: form })
  },
  confirmImport(items) {
    return request('/api/inspirations/import/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items }),
    })
  },

  // 分析对象为他山坊当前观点（viewpoints 表内容）；reset 时后端先清空打磨阶段对话再生成
  analyzeViewpoint: (id, reset = false) =>
    request(`/api/viewpoints/${id}/analysis${reset ? '?reset=1' : ''}`, { method: 'POST' }),

  suggestTitle(content) {
    return request('/api/ai/title-suggestion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    })
  },

  checkViewpoint: (sessionId) =>
    request(`/api/review/sessions/${sessionId}/viewpoint-check`, { method: 'POST' }),
  enterPolish(sessionId, draft) {
    return request(`/api/review/sessions/${sessionId}/enter-polish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ draft }),
    })
  },

  postOpeningQuestion(sessionId, regenerate = false, polishEntry = false) {
    const params = new URLSearchParams()
    if (regenerate) params.set('regenerate', 'true')
    if (polishEntry) params.set('polish_entry', 'true')
    const qs = params.toString()
    return request(`/api/review/sessions/${sessionId}/opening${qs ? `?${qs}` : ''}`, { method: 'POST' })
  },
  getReviewQueue: () => request('/api/review/queue'),
  startReviewSession(viewpointId) {
    return request('/api/review/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ viewpoint_id: viewpointId }),
    })
  },
  getActiveSession: () => request('/api/review/sessions/active'),
  // 消息级撤销：删当前阶段最后一条消息（AI 回复连同其用户提问）
  undoReviewSession: (id) =>
    request(`/api/review/sessions/${id}/undo`, { method: 'POST' }),
  // 阶段级回退：polish→distill 清分析与打磨消息；distill→重置清空并恢复观点原文
  undoReviewPhase: (id) =>
    request(`/api/review/sessions/${id}/undo-phase`, { method: 'POST' }),
  sendReviewMessage(id, payload) {
    return request(`/api/review/sessions/${id}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  submitReviewDecision(id, payload) {
    return request(`/api/review/sessions/${id}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },

  getViewpoint: (id) => request(`/api/viewpoints/${id}`),

  listViewpoints(filters = {}) {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(filters)) {
      if (value) params.set(key, value)
    }
    const qs = params.toString()
    return request(`/api/viewpoints${qs ? `?${qs}` : ''}`)
  },
  listViewpointRelations: (id) => request(`/api/viewpoints/${id}/relations`),
  createViewpointRelation(id, payload) {
    return request(`/api/viewpoints/${id}/relations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  deleteViewpointRelation(id, relationId) {
    return request(`/api/viewpoints/${id}/relations/${relationId}`, {
      method: 'DELETE',
    })
  },
  // 撤回：accepted → draft，观点回他山坊打磨队列（会话重开回打磨最后状态）
  withdrawViewpoint: (id) =>
    request(`/api/viewpoints/${id}/withdraw`, { method: 'POST' }),
  updateViewpointTitle(id, payload) {
    return request(`/api/viewpoints/${id}/title`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  getReviewHistory: (id) => request(`/api/viewpoints/${id}/review-history`),
  getClassifiedViewpoints: () => request('/api/viewpoints/classified'),

  getInspiration: (id) => request(`/api/inspirations/${id}`),

  getLlmSettings: () => request('/api/settings/llm'),
  getAiStatus: () => request('/api/ai/status'),
  reconcileAi: () => request('/api/ai/reconcile', { method: 'POST' }),
  saveLlmSettings: (payload) =>
    request('/api/settings/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  testLlmSettings: (payload) =>
    request('/api/settings/llm/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload ?? {}),
    }),
}
