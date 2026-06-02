/**
 * 用户会话：用 pinia-plugin-persistedstate 持久化，启动时校验 token 有效性。
 */
import { defineStore } from 'pinia'
import { authApi } from '@/api/modules'

export const useSessionStore = defineStore('session', {
  state: () => ({
    user: null,
    token: '',
    refreshToken: '',
    expiresIn: 0,
  }),
  getters: {
    isAuthenticated: (s) => Boolean(s.token && s.user),
    isAdmin: (s) => ['admin', 'superadmin'].includes(s.user?.role),
    isSuperAdmin: (s) => s.user?.role === 'superadmin',
  },
  actions: {
    async login(payload) {
      const data = await authApi.login(payload)
      this.setSession(data)
    },
    async register(payload) {
      const data = await authApi.register(payload)
      this.setSession(data)
    },
    async refreshMe() {
      try {
        this.user = await authApi.me()
      } catch {
        this.logout()
      }
    },
    async logoutRemote() {
      try {
        await authApi.logout()
      } catch {
        // 忽略；前端清理始终执行
      } finally {
        this.logout()
      }
    },
    setSession(data) {
      this.user = data.user || null
      this.token = data.access_token || ''
      this.refreshToken = data.refresh_token || ''
      this.expiresIn = data.expires_in || 0
    },
    logout() {
      this.user = null
      this.token = ''
      this.refreshToken = ''
      this.expiresIn = 0
    },
  },
  persist: {
    key: 'aimi-session',
    storage: localStorage,
    pick: ['user', 'token', 'refreshToken', 'expiresIn'],
  },
})
