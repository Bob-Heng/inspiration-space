// 开发模式（vite 5173）跨端口访问后端；打包后由后端同源托管，用相对路径
const BASE_URL = import.meta.env.DEV ? 'http://localhost:8000' : ''

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(BASE_URL + path, {
      credentials: 'include',
      ...options,
    })
  } catch {
    throw new ApiError(0, '无法连接后端，请确认后端已启动（可双击 启动.bat）')
  }
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(res.status, data?.detail ?? `请求失败（${res.status}）`)
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
  setup(username, password) {
    return request('/api/auth/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
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

  analyzeInspiration: (id) =>
    request(`/api/inspirations/${id}/analysis`, { method: 'POST' }),

  startReviewSession(inspirationId) {
    return request('/api/review/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ inspiration_id: inspirationId }),
    })
  },
  getActiveSession: () => request('/api/review/sessions/active'),
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
  mergeViewpoint(id, payload) {
    return request(`/api/viewpoints/${id}/merge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  splitViewpoint(id, payload) {
    return request(`/api/viewpoints/${id}/split`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  updateViewpointStatus(id, payload) {
    return request(`/api/viewpoints/${id}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  getViewpointHistory: (id) => request(`/api/viewpoints/${id}/history`),
  getClassifiedViewpoints: () => request('/api/viewpoints/classified'),

  getInspiration: (id) => request(`/api/inspirations/${id}`),

  getLlmSettings: () => request('/api/settings/llm'),
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
