import { api, uploadApi, apiBaseURL, authHeaders, on401Logout } from './client'

// ========== 客户端 API ==========
export const authApi = {
  register: (payload) => api.post('/auth/register', payload),
  login: (payload) => api.post('/auth/login', payload),
  refresh: (refresh_token) => api.post('/auth/refresh', { refresh_token }),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  updateMe: (payload) => api.put('/auth/me', payload),
  changePassword: (payload) => api.post('/auth/me/change-password', payload),
}

export const resumeApi = {
  list: (params = {}) => api.get('/resumes', { params }),
  get: (id) => api.get(`/resumes/${id}`),
  createText: (payload) => api.post('/resumes', payload),
  upload: (formData, onProgress) =>
    uploadApi.post('/resumes/upload', formData, {
      onUploadProgress: (e) => onProgress?.(e.total ? e.loaded / e.total : 0),
    }),
  delete: (id) => api.delete(`/resumes/${id}`),
}

export const jobApi = {
  list: () => api.get('/jobs'),
  recommend: (payload) => api.post('/jobs/recommend', payload),
}

async function streamSse(path, { params = {}, signal, onEvent } = {}) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const url = `${apiBaseURL}${path}${search.toString() ? `?${search}` : ''}`
  const response = await fetch(url, {
    method: 'GET',
    headers: authHeaders(),
    signal,
  })
  if (response.status === 401) {
    on401Logout()
    throw new Error('登录已过期')
  }
  if (!response.ok || !response.body) {
    throw new Error(`流式请求失败：${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const lines = block.split('\n')
      const eventLine = lines.find((line) => line.startsWith('event: '))
      const dataLine = lines.find((line) => line.startsWith('data: '))
      if (!eventLine || !dataLine) continue
      const event = eventLine.slice(7).trim()
      const data = JSON.parse(dataLine.slice(6))
      onEvent?.({ event, data })
    }
  }
}

export const interviewApi = {
  list: (params = {}) => api.get('/interviews', { params }),
  get: (id) => api.get(`/interviews/${id}`),
  create: (payload) => api.post('/interviews', payload),
  answer: (id, payload) => api.post(`/interviews/${id}/answers`, payload),
  turn: (id, payload) => api.post(`/interviews/${id}/turns`, payload),
  finish: (id) => api.post(`/interviews/${id}/finish`),
  cancel: (id) => api.post(`/interviews/${id}/cancel`),
  delete: (id) => api.delete(`/interviews/${id}`),
  stream: (id, options) => streamSse(`/interviews/${id}/stream`, options),
}

export const reportApi = {
  get: (interviewId) => api.get(`/reports/${interviewId}`),
}

export const ragApi = {
  search: (payload) => api.post('/rag/search', payload),
}

// ========== 后台管理 API ==========
export const adminApi = {
  // 用户
  listUsers: (params) => api.get('/admin/users', { params }),
  toggleUser: (id, is_active) =>
    api.put(`/admin/users/${id}/toggle-active`, { is_active }),
  userStats: () => api.get('/admin/users/stats'),

  // 面试
  listInterviews: (params) => api.get('/admin/interviews', { params }),
  interviewStats: () => api.get('/admin/interviews/stats'),

  // 岗位
  listJobs: () => api.get('/admin/jobs'),
  createJob: (payload) => api.post('/admin/jobs', payload),
  updateJob: (id, payload) => api.put(`/admin/jobs/${id}`, payload),
  deleteJob: (id) => api.delete(`/admin/jobs/${id}`),
  toggleJob: (id, is_active) =>
    api.patch(`/admin/jobs/${id}/toggle`, null, { params: { is_active } }),

  // RAG
  listRagDocs: (params) => api.get('/admin/rag/documents', { params }),
  createRagDoc: (payload) => api.post('/admin/rag/documents', payload),
  uploadRagDoc: (formData) =>
    uploadApi.post('/admin/rag/documents/upload', formData),
  updateRagDoc: (id, payload) => api.put(`/admin/rag/documents/${id}`, payload),
  deleteRagDoc: (id) => api.delete(`/admin/rag/documents/${id}`),
  listRagChunks: (id, params) =>
    api.get(`/admin/rag/documents/${id}/chunks`, { params }),
  toggleRagDoc: (id, is_active) =>
    api.patch(`/admin/rag/documents/${id}/toggle`, null, {
      params: { is_active },
    }),
  reindexRagDoc: (id) => api.post(`/admin/rag/documents/${id}/reindex`),
  testRetrieve: (payload) => api.post('/admin/rag/test-retrieve', payload),
  ragStats: () => api.get('/admin/rag/stats'),

  // AI 配置
  getAiConfig: () => api.get('/admin/ai/config'),
  updateAiConfig: (payload) => api.put('/admin/ai/config', payload),
  testAiConfig: () => api.post('/admin/ai/config/test'),
  getAiUsageSummary: (params = {}) => api.get('/admin/ai/usage/summary', { params }),
  listAiUsage: (params = {}) => api.get('/admin/ai/usage', { params }),
  getAiFailureOverview: (params = {}) =>
    api.get('/admin/ai/failures/overview', { params }),
}
