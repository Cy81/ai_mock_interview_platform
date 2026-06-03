<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  Briefcase,
  ClipboardList,
  FileText,
  LogOut,
  MessageSquareText,
  ShieldCheck,
  Target,
} from 'lucide-vue-next'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const menus = [
  { to: '/', label: '面试记录', icon: ClipboardList },
  { to: '/resumes', label: '上传简历', icon: FileText },
  { to: '/jobs', label: '岗位匹配', icon: Briefcase },
  { to: '/interviews', label: 'AI 面试', icon: MessageSquareText },
  { to: '/reports', label: '评分报告', icon: ClipboardList },
]

const pageTitle = computed(() => route.meta.title || '面试记录')
const showPageHead = computed(() => route.name !== 'dashboard')

function isActive(item) {
  if (item.to === '/') return route.path === '/'
  return route.path.startsWith(item.to)
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
  } catch (_) {
    // 用户取消退出
  }
}
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
  .admin-entry {
    display: none;
  }

  .client-main {
    padding-top: 18px;
  }
}
</style>
