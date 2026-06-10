<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  AlertCircle,
  Briefcase,
  ClipboardList,
  FileText,
  LifeBuoy,
  LogOut,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  Target,
  Wifi,
  WifiOff,
} from 'lucide-vue-next'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const supportVisible = ref(false)
const checkingStatus = ref(false)
const serviceStatus = ref({
  online: typeof navigator === 'undefined' ? true : navigator.onLine,
  api: 'checking',
  ready: 'checking',
  message: '正在检查服务状态',
  checkedAt: '',
})
let statusTimer = null

const menus = [
  { to: '/', label: '面试记录', icon: ClipboardList },
  { to: '/resumes', label: '上传简历', icon: FileText },
  { to: '/jobs', label: '岗位匹配', icon: Briefcase },
  { to: '/interviews', label: 'AI 面试', icon: MessageSquareText },
  { to: '/reports', label: '评分报告', icon: ClipboardList },
]

const pageTitle = computed(() => route.meta.title || '面试记录')
const showPageHead = computed(() => route.name !== 'dashboard' && !route.meta.immersive)
const statusTone = computed(() => {
  if (!serviceStatus.value.online || serviceStatus.value.api === 'down') return 'danger'
  if (serviceStatus.value.ready === 'degraded') return 'warning'
  if (serviceStatus.value.api === 'ok') return 'success'
  return 'info'
})
const statusIcon = computed(() => {
  if (!serviceStatus.value.online || serviceStatus.value.api === 'down') return WifiOff
  if (serviceStatus.value.ready === 'degraded') return AlertCircle
  return Wifi
})
const statusText = computed(() => {
  if (!serviceStatus.value.online) return '当前网络离线'
  if (serviceStatus.value.api === 'down') return '后端服务不可达'
  if (serviceStatus.value.ready === 'degraded') return '服务可用，依赖检查异常'
  if (serviceStatus.value.api === 'ok') return '服务运行正常'
  return '正在检查服务'
})

function isActive(item) {
  if (item.to === '/') return route.path === '/'
  return route.path.startsWith(item.to)
}

async function checkSystemStatus() {
  checkingStatus.value = true
  const online = typeof navigator === 'undefined' ? true : navigator.onLine
  serviceStatus.value.online = online
  if (!online) {
    serviceStatus.value = {
      ...serviceStatus.value,
      api: 'down',
      ready: 'degraded',
      message: '网络已断开，草稿仍会保存在本机',
      checkedAt: new Date().toLocaleTimeString(),
    }
    checkingStatus.value = false
    return
  }

  try {
    const health = await fetch('/healthz', { cache: 'no-store' })
    let ready = null
    try {
      ready = await fetch('/readyz', { cache: 'no-store' })
    } catch {
      ready = null
    }
    serviceStatus.value = {
      online,
      api: health.ok ? 'ok' : 'down',
      ready: ready?.ok ? 'ok' : 'degraded',
      message: health.ok
        ? '核心 API 可访问，面试草稿会自动保存'
        : '核心 API 暂时不可访问，请稍后重试',
      checkedAt: new Date().toLocaleTimeString(),
    }
  } catch {
    serviceStatus.value = {
      online,
      api: 'down',
      ready: 'degraded',
      message: '无法连接后端服务，请检查网络或稍后重试',
      checkedAt: new Date().toLocaleTimeString(),
    }
  } finally {
    checkingStatus.value = false
  }
}

async function logout() {
  try {
    await ElMessageBox.confirm('确定退出登录吗？', '退出确认', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await session.logoutRemote()
    router.replace('/login')
  } catch {
    // 用户取消退出
  }
}

onMounted(() => {
  checkSystemStatus()
  window.addEventListener('online', checkSystemStatus)
  window.addEventListener('offline', checkSystemStatus)
  statusTimer = window.setInterval(checkSystemStatus, 60000)
})

onUnmounted(() => {
  window.removeEventListener('online', checkSystemStatus)
  window.removeEventListener('offline', checkSystemStatus)
  if (statusTimer) window.clearInterval(statusTimer)
})
</script>

<template>
  <div class="client-shell">
    <header class="client-topnav">
      <div class="nav-inner">
        <RouterLink to="/" class="brand-link">
          <span class="brand-mark"><Target :size="18" /></span>
          <span class="brand-name">智面</span>
        </RouterLink>

        <nav class="primary-nav" aria-label="用户端导航">
          <RouterLink
            v-for="item in menus"
            :key="item.to"
            :to="item.to"
            class="nav-link"
            :class="{ active: isActive(item) }"
          >
            <component :is="item.icon" :size="16" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </nav>

        <div class="nav-actions">
          <el-button
            v-if="session.isAdmin"
            class="admin-entry"
            plain
            :icon="ShieldCheck"
            @click="router.push('/admin')"
          >
            管理端
          </el-button>
          <el-button class="support-entry" plain :icon="LifeBuoy" @click="supportVisible = true">
            帮助
          </el-button>

          <button
            type="button"
            class="quiet-status-pill"
            :class="`status-${statusTone}`"
            @click="supportVisible = true"
          >
            <component :is="statusIcon" :size="13" />
            <span>{{ statusText }}</span>
          </button>

          <el-dropdown>
            <button class="profile-chip" type="button">
              <el-avatar :size="32" :src="session.user?.avatar_url">
                {{ session.user?.full_name?.slice(0, 1) || 'U' }}
              </el-avatar>
              <span class="profile-name">{{ session.user?.full_name || '候选人' }}</span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="router.push('/resumes')">上传简历</el-dropdown-item>
                <el-dropdown-item @click="router.push('/jobs')">岗位匹配</el-dropdown-item>
                <el-dropdown-item @click="router.push('/reports')">我的报告</el-dropdown-item>
                <el-dropdown-item v-if="session.isAdmin" divided @click="router.push('/admin')">
                  管理后台
                </el-dropdown-item>
                <el-dropdown-item divided @click="logout">
                  <LogOut :size="14" /> 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </header>

    <main class="client-main">
      <section v-if="showPageHead" class="client-page-head">
        <p>AI MOCK INTERVIEW</p>
        <h1>{{ pageTitle }}</h1>
      </section>

      <RouterView v-slot="{ Component }">
        <transition name="fade-slide" mode="out-in">
          <component :is="Component" />
        </transition>
      </RouterView>
    </main>

    <el-drawer v-model="supportVisible" title="帮助与支持" size="360px" class="support-drawer">
      <div class="support-content">
        <section>
          <h3>服务状态</h3>
          <p>{{ statusText }}。{{ serviceStatus.message }}</p>
          <el-button text :icon="RefreshCw" :loading="checkingStatus" @click="checkSystemStatus">
            重新检查
          </el-button>
        </section>
        <section>
          <h3>面试前检查</h3>
          <ul>
            <li>确认简历已经解析完成。</li>
            <li>选择目标岗位后再开始 AI 面试。</li>
            <li>回答会自动保存草稿，刷新页面后可继续。</li>
          </ul>
        </section>
        <section>
          <h3>遇到异常</h3>
          <p>先刷新服务状态；如果 API 不可达，等待后端恢复后再继续。已提交的面试记录不会丢失。</p>
        </section>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.client-shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(64, 150, 255, 0.12), transparent 32rem),
    linear-gradient(180deg, #f8fbff 0%, #f4f6f9 42%, #eef2f6 100%);
}

.client-topnav {
  position: sticky;
  top: 0;
  z-index: 20;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(18px);
}

.nav-inner {
  width: min(1180px, calc(100% - 32px));
  min-height: 64px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 22px;
}

.brand-link {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  color: #172033;
  font-weight: 800;
}

.brand-mark {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: #fff;
  background: linear-gradient(135deg, #ff4f81, #3b82f6 58%, #15b8a6);
  box-shadow: 0 10px 24px rgba(59, 130, 246, 0.22);
}

.brand-name {
  font-size: 18px;
}

.primary-nav {
  display: flex;
  justify-content: center;
  gap: 4px;
  min-width: 0;
}

.nav-link {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 12px;
  border-radius: 8px;
  color: #5f6f89;
  font-size: 14px;
  font-weight: 600;
  transition:
    color 0.18s ease,
    background 0.18s ease,
    transform 0.18s ease;
}

.nav-link:hover {
  color: #1d4ed8;
  background: #edf5ff;
  transform: translateY(-1px);
}

.nav-link.active {
  color: #1d4ed8;
  background: #e8f1ff;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.admin-entry {
  border-radius: 8px;
}

.support-entry {
  border-radius: 8px;
}

.quiet-status-pill {
  height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid #dbe5ef;
  border-radius: 999px;
  color: #5f6f89;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 700;
}

.quiet-status-pill.status-success {
  color: #0f766e;
  border-color: #b7eadc;
  background: #f0fdf8;
}

.quiet-status-pill.status-warning {
  color: #b45309;
  border-color: #fed7aa;
  background: #fff7ed;
}

.quiet-status-pill.status-danger {
  color: #be123c;
  border-color: #fecdd3;
  background: #fff1f2;
}

.profile-chip {
  height: 40px;
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 4px 10px 4px 4px;
  border: 1px solid #dce3ee;
  border-radius: 999px;
  color: #344256;
  background: #fff;
  cursor: pointer;
}

.profile-name {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
}

.client-main {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 28px 0 48px;
}

.support-content {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.support-content h3 {
  margin: 0 0 8px;
  color: #172033;
  font-size: 15px;
}

.support-content p,
.support-content li {
  color: #5f6f89;
  font-size: 13px;
  line-height: 1.7;
}

.support-content ul {
  margin: 0;
  padding-left: 18px;
}

.client-page-head {
  margin-bottom: 18px;
}

.client-page-head p {
  margin: 0 0 4px;
  color: #8a97aa;
  font-size: 12px;
  font-weight: 700;
}

.client-page-head h1 {
  margin: 0;
  color: #172033;
  font-size: 28px;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@media (max-width: 900px) {
  .nav-inner {
    grid-template-columns: 1fr;
    gap: 10px;
    padding: 12px 0;
  }

  .primary-nav {
    justify-content: flex-start;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .nav-actions {
    justify-content: space-between;
  }
}

@media (max-width: 640px) {
  .nav-inner,
  .client-main {
    width: min(100% - 20px, 1180px);
  }

  .profile-name,
  .admin-entry,
  .support-entry,
  .quiet-status-pill span {
    display: none;
  }

  .client-main {
    padding-top: 18px;
  }
}
</style>
