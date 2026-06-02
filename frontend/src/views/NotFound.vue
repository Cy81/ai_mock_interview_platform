<script setup>
/** 404：路径不存在或资源已删除。 */
import { useRouter } from 'vue-router'
import { Compass } from 'lucide-vue-next'

const router = useRouter()
</script>

<template>
  <main class="error-screen">
    <div class="error-card">
      <Compass :size="42" />
      <h1>404 · 页面走丢了</h1>
      <p>你访问的地址不存在，或资源已被移除。可以返回工作台或上一页。</p>
      <div class="actions">
        <el-button type="primary" @click="router.replace('/')">返回工作台</el-button>
        <el-button @click="router.back()">返回上一页</el-button>
      </div>
    </div>
  </main>
</template>

<style scoped>
.error-screen {
  min-height: 100vh; display: grid; place-items: center;
  background: linear-gradient(160deg, #e0f2fe, #ede9fe);
  padding: 24px;
}
.error-card {
  background: #fff; border-radius: 18px; padding: 48px 40px; max-width: 460px;
  box-shadow: 0 20px 50px -25px rgba(0,0,0,.2); text-align: center;
}
.error-card h1 { margin: 16px 0 8px; color: #0f172a; }
.error-card p { color: #475569; margin: 0 0 18px; line-height: 1.6; }
.actions { display: flex; gap: 12px; justify-content: center; }
</style>
