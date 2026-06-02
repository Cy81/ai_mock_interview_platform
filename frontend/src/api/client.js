/**
 * Axios 实例：
 * - 请求自动注入 Bearer；
 * - 响应根据 status 转换错误（401 自动清 session 并跳登录）；
 * - 上传走独立的更长超时；
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useSessionStore } from '@/stores/session'
import router from '@/router'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL,
  timeout: 30000,
})

export const uploadApi = axios.create({
  baseURL,
  timeout: 120000,
  headers: { 'Content-Type': 'multipart/form-data' },
})

function injectAuth(config) {
  const session = useSessionStore()
  if (session.token) {
    config.headers.Authorization = `Bearer ${session.token}`
  }
  return config
}

function onError(error) {
  const status = error.response?.status
  const detail = error.response?.data?.detail || error.message || '请求失败'

  if (status === 401) {
    const session = useSessionStore()
    session.logout()
    if (router.currentRoute.value.name !== 'login') {
      router.replace({
        name: 'login',
        query: { redirect: router.currentRoute.value.fullPath },
      })
    }
  } else if (status === 403) {
    ElMessage.error(detail || '无权访问')
  } else if (status >= 500) {
    ElMessage.error('服务器错误，请稍后重试')
  } else if (status === 422 && Array.isArray(error.response?.data?.errors)) {
    const first = error.response.data.errors[0]
    ElMessage.error(`${first.field || '请求'}：${first.message}`)
  } else if (detail) {
    ElMessage.error(detail)
  }
  return Promise.reject(new Error(detail))
}

;[api, uploadApi].forEach((instance) => {
  instance.interceptors.request.use(injectAuth)
  instance.interceptors.response.use((r) => r.data, onError)
})

export function on401Logout() {
  // 给非 axios 调用（比如 SSE）一个直接退出的入口
  const session = useSessionStore()
  session.logout()
  router.replace({ name: 'login' })
}
