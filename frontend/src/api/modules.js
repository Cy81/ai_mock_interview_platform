import { api, uploadApi } from './client'

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

export const interviewApi = {
  list: (params = {}) => api.get('/interviews', { params }),
  get: (id) => api.get(`/interviews/${id}`),
  create: (payload) => api.post('/interviews', payload),
  answer: (id, payload) => api.post(`/interviews/${id}/answers`, payload),
  finish: (id) => api.post(`/interviews/${id}/finish`),
  cancel: (id) => api.post(`/interviews/${id}/cancel`),
  delete: (id) => api.delete(`/interviews/${id}`),
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
  toggleRagDoc: (id, is_active) =>
    api.patch(`/admin/rag/documents/${id}/toggle`, null, {
      params: { is_active },
    }),
  reindexRagDoc: (id) => api.post(`/admin/rag/documents/${id}/reindex`),
  testRetrieve: (payload) => api.post('/admin/rag/test-retrieve', payload),
  ragStats: () => api.get('/admin/rag/stats'),
}
