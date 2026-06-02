<script setup>
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  Activity,
  Briefcase,
  Database,
  Home,
  LogOut,
  Users,
  ChevronLeft,
} from 'lucide-vue-next'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const menus = [
  { to: '/admin', label: '总览', icon: Home, exact: true },
  { to: '/admin/users', label: '用户管理', icon: Users },
  { to: '/admin/jobs', label: '岗位管理', icon: Briefcase },
  { to: '/admin/rag', label: 'RAG 知识库', icon: Database },
  { to: '/admin/interviews', label: '面试记录', icon: Activity },
]

const title = computed(() => route.meta.title || '后台总览')

async function logout() {
  await session.logoutRemote()
  router.replace('/login')
}
</script>

<template>
  <el-container class="admin-shell">
    <el-aside width="240px" class="sidebar">
      <div class="brand">
        <strong>AIMI</strong>
        <span>Backoffice</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#0b1220"
        text-color="#94a3b8"
        active-text-color="#fff"
      >
        <el-menu-item v-for="m in menus" :key="m.to" :index="m.to">
          <component :is="m.icon" :size="18" />
          <template #title>{{ m.label }}</template>
        </el-menu-item>
      </el-menu>

      <el-button class="back-btn" link @click="router.push('/')">
        <ChevronLeft :size="14" /> 返回客户端
      </el-button>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div>
          <p class="eyebrow">BACKOFFICE</p>
          <h1>{{ title }}</h1>
        </div>
        <div class="actions">
          <el-tag type="warning" effect="dark">{{ session.user?.role?.toUpperCase() }}</el-tag>
          <span>{{ session.user?.email }}</span>
          <el-button type="danger" plain :icon="LogOut" @click="logout">退出</el-button>
        </div>
      </el-header>

      <el-main>
        <RouterView />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-shell { height: 100vh; }
.sidebar {
  background: #0b1220;
  color: #94a3b8;
  display: flex;
  flex-direction: column;
}
.sidebar :deep(.el-menu) { border: 0; flex: 1; }
.brand {
  padding: 20px;
  border-bottom: 1px solid #1e293b;
  color: #f8fafc;
}
.brand strong { font-size: 18px; letter-spacing: 1px; }
.brand span { display: block; color: #64748b; letter-spacing: 4px; font-size: 11px; }
.back-btn { color: #64748b; padding: 12px; }
.topbar {
  background: #fff;
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid #e2e8f0;
}
.topbar .eyebrow { font-size: 11px; letter-spacing: 2px; color: #94a3b8; margin: 0; }
.topbar h1 { font-size: 18px; margin: 2px 0 0; color: #0f172a; }
.actions { display: flex; align-items: center; gap: 12px; color: #475569; font-size: 13px; }
</style>
