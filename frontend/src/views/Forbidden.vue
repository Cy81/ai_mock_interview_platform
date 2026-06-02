<script setup>
/** 403：用户已登录但角色不足。提供回客户端 / 退出登录两条出口。 */
import { useRouter } from 'vue-router'
import { ShieldAlert } from 'lucide-vue-next'
import { useSessionStore } from '@/stores/session'

const router = useRouter()
const session = useSessionStore()

async function logoutAndBack() {
  await session.logoutRemote()
  router.replace('/login')
}
</script>

<template>
  <main class="error-screen">
    <div class="error-card">
      <ShieldAlert :size="42" />
      <h1>403 · 无权访问</h1>
      <p>当前账号 {{ session.user?.email || '匿名' }} 没有访问该页面所需的角色。</p>
      <div class="actions">
        <el-button type="primary" @click="router.replace('/')">返回工作台</el-button>
        <el-button @click="logoutAndBack">切换账号</el-button>
      </div>
    </div>
  </main>
</template>

<style scoped>
.error-screen {
  min-height: 100vh; display: grid; place-items: center;
  background: linear-gradient(160deg, #fef3c7, #fee2e2);
  padding: 24px;
}
.error-card {
  background: #fff; border-radius: 18px; padding: 48px 40px; max-width: 460px;
  box-shadow: 0 20px 50px -25px rgba(0,0,0,.2); text-align: center;
}
.error-card h1 { margin: 16px 0 8px; color: #b91c1c; }
.error-card p { color: #475569; margin: 0 0 18px; line-height: 1.6; }
.actions { display: flex; gap: 12px; justify-content: center; }
</style>
