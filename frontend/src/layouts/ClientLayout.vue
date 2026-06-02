<script setup>
import { computed, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  BarChart3,
  Briefcase,
  ClipboardCheck,
  FileText,
  Layers,
  LogOut,
  Menu,
  MessageSquareText,
  ShieldCheck,
} from 'lucide-vue-next'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const collapsed = ref(false)

const menus = [
  { to: '/', label: '工作台', icon: BarChart3 },
  { to: '/resumes', label: '简历解析', icon: FileText },
  { to: '/jobs', label: '岗位匹配', icon: Briefcase },
  { to: '/interviews', label: '模拟面试', icon: MessageSquareText },
  { to: '/reports', label: '评分报告', icon: ClipboardCheck },
]

const breadcrumb = computed(() => route.meta.title || '工作台')

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
    // 取消
  }
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside :width="collapsed ? '64px' : '240px'" class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <Layers :size="22" />
        </div>
        <transition name="fade">
          <div v-if="!collapsed" class="brand-text">
            <strong>AIMI</strong>
            <small>Interview OS</small>
          </div>
        </transition>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        background-color="#0f172a"
        text-color="#cbd5e1"
        active-text-color="#fff"
      >
        <el-menu-item v-for="m in menus" :key="m.to" :index="m.to">
          <component :is="m.icon" :size="18" />
          <template #title>{{ m.label }}</template>
        </el-menu-item>
        <el-menu-item v-if="session.isAdmin" index="/admin">
          <ShieldCheck :size="18" />
          <template #title>进入管理后台</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="topbar-left">
          <el-button text :icon="Menu" @click="collapsed = !collapsed" />
          <div class="title-block">
            <p class="eyebrow">AI MOCK INTERVIEW PLATFORM</p>
            <h1>{{ breadcrumb }}</h1>
          </div>
        </div>

        <el-dropdown>
          <div class="user-card">
            <el-avatar :size="36" :src="session.user?.avatar_url">
              {{ session.user?.full_name?.slice(0, 1) || 'U' }}
            </el-avatar>
            <div class="user-meta">
              <strong>{{ session.user?.full_name || '候选人' }}</strong>
              <small>{{ session.user?.email }}</small>
            </div>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="router.push('/jobs')">岗位推荐</el-dropdown-item>
              <el-dropdown-item @click="router.push('/reports')">我的报告</el-dropdown-item>
              <el-dropdown-item v-if="session.isAdmin" @click="router.push('/admin')">
                管理后台
              </el-dropdown-item>
              <el-dropdown-item divided @click="logout">
                <LogOut :size="14" /> 退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <el-main>
        <RouterView v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-shell { height: 100vh; }
.sidebar {
  background: #0f172a;
  color: #cbd5e1;
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease;
}
.sidebar :deep(.el-menu) { border: 0; }
.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 22px 18px;
  border-bottom: 1px solid #1e293b;
}
.brand-mark {
  width: 36px; height: 36px;
  background: linear-gradient(135deg,#3b82f6,#8b5cf6);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  color: white;
}
.brand-text strong { color: #f1f5f9; font-size: 16px; }
.brand-text small { display: block; color: #64748b; font-size: 11px; letter-spacing: 1px; }
.topbar {
  background: #fff;
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid #e2e8f0;
}
.topbar-left { display: flex; align-items: center; gap: 14px; }
.title-block .eyebrow { font-size: 11px; letter-spacing: 1.5px; color: #94a3b8; margin: 0; }
.title-block h1 { font-size: 20px; margin: 2px 0 0; color: #0f172a; }
.user-card { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.user-meta strong { color: #0f172a; font-size: 13px; }
.user-meta small { display: block; color: #94a3b8; font-size: 11px; }
.fade-slide-enter-active, .fade-slide-leave-active { transition: opacity .2s ease, transform .2s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateY(8px); }
.fade-slide-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
