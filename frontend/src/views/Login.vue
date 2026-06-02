<script setup>
/**
 * 登录 / 注册：
 *  - el-form + 异步校验，密码至少 8 位且包含字母与数字；
 *  - 处理 ?redirect= 回跳，登录后回到原页；
 *  - 错误信息分两类：表单校验（行内）和后端业务（顶部 Alert）。
 */
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { LogIn, ShieldCheck, Sparkles, UserPlus } from 'lucide-vue-next'
import { useSessionStore } from '@/stores/session'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const mode = ref('login')
const loading = ref(false)
const submitError = ref('')
const formRef = ref(null)

const form = reactive({
  email: '',
  full_name: '',
  password: '',
})

const passwordValidator = (_rule, value, callback) => {
  if (!value) return callback(new Error('请输入密码'))
  if (value.length < 8) return callback(new Error('密码至少 8 位'))
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value))
    return callback(new Error('需同时包含字母与数字'))
  callback()
}

const rules = computed(() => ({
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  full_name:
    mode.value === 'register'
      ? [{ required: true, min: 2, max: 30, message: '姓名 2~30 字', trigger: 'blur' }]
      : [],
  password: [{ validator: passwordValidator, trigger: 'blur' }],
}))

async function submit() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  loading.value = true
  submitError.value = ''
  try {
    if (mode.value === 'login') {
      await session.login({ email: form.email.trim(), password: form.password })
    } else {
      await session.register({
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
      })
    }
    ElMessage.success(mode.value === 'login' ? '登录成功' : '注册成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    router.replace(redirect.startsWith('/') ? redirect : '/')
  } catch (err) {
    submitError.value = err?.message || '操作失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function toggleMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  submitError.value = ''
  formRef.value?.clearValidate()
}
</script>

<template>
  <main class="login-screen">
    <section class="login-card">
      <aside class="hero">
        <div class="hero-badge"><Sparkles :size="14" /> AIMI Interview OS</div>
        <h1>把简历、岗位、知识库与面试评分串成闭环。</h1>
        <p>覆盖 候选人、面试官、运营 三类角色，企业级双 RAG 与 LangChain Agent 组合。</p>
        <ul>
          <li><ShieldCheck :size="16" /> JWT + 角色策略 + 失败锁定</li>
          <li><ShieldCheck :size="16" /> Celery 异步打分 / Embedding 批量入库</li>
          <li><ShieldCheck :size="16" /> 统一观测：结构化日志 / Prometheus / Sentry</li>
        </ul>
      </aside>

      <el-form
        ref="formRef"
        class="login-form"
        :model="form"
        :rules="rules"
        label-position="top"
        @submit.prevent="submit"
      >
        <header class="login-header">
          <div>
            <p class="eyebrow">{{ mode === 'login' ? '欢迎回来' : '创建账号' }}</p>
            <h2>{{ mode === 'login' ? '登录平台' : '注册新账号' }}</h2>
          </div>
          <el-button text type="primary" @click="toggleMode">
            {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
          </el-button>
        </header>

        <el-alert
          v-if="submitError"
          type="error"
          :closable="false"
          show-icon
          :title="submitError"
          style="margin-bottom: 12px"
        />

        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="you@company.com" autocomplete="email" />
        </el-form-item>

        <el-form-item v-if="mode === 'register'" label="姓名" prop="full_name">
          <el-input v-model="form.full_name" placeholder="2-30 字" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="mode === 'register' ? '至少 8 位，含字母与数字' : '请输入密码'"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          :loading="loading"
          native-type="submit"
          style="width: 100%"
        >
          <component :is="mode === 'login' ? LogIn : UserPlus" :size="16" />
          <span style="margin-left: 6px">
            {{ mode === 'login' ? '登录' : '注册并登录' }}
          </span>
        </el-button>

        <p class="hint">
          管理员账号请联系超级管理员开通；登录后可在右上角切换到管理后台。
        </p>
      </el-form>
    </section>
  </main>
</template>

<style scoped>
.login-screen {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background:
    radial-gradient(1200px 600px at 80% -10%, rgba(59, 130, 246, 0.18), transparent 60%),
    radial-gradient(900px 500px at -10% 110%, rgba(139, 92, 246, 0.18), transparent 60%),
    #0b1220;
  padding: 32px 16px;
}
.login-card {
  width: min(960px, 100%);
  background: #fff;
  border-radius: 24px;
  box-shadow: 0 30px 60px -20px rgba(15, 23, 42, 0.4);
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  overflow: hidden;
}
.hero {
  background: linear-gradient(160deg, #0f172a 0%, #1e293b 60%, #312e81 100%);
  color: #e2e8f0;
  padding: 42px 36px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 18px;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  width: fit-content;
  font-size: 12px;
  letter-spacing: 1px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  color: #f8fafc;
}
.hero h1 {
  font-size: 26px;
  line-height: 1.4;
  margin: 0;
  color: #f8fafc;
}
.hero p { color: #cbd5e1; line-height: 1.7; margin: 0; }
.hero ul { list-style: none; padding: 0; margin: 4px 0 0; display: grid; gap: 10px; }
.hero li { display: flex; align-items: center; gap: 8px; color: #cbd5e1; font-size: 13px; }
.login-form { padding: 42px 40px; display: flex; flex-direction: column; }
.login-header {
  display: flex; justify-content: space-between; align-items: flex-end;
  margin-bottom: 18px;
}
.login-header .eyebrow {
  font-size: 11px; letter-spacing: 2px; color: #94a3b8; margin: 0 0 4px;
}
.login-header h2 { margin: 0; color: #0f172a; font-size: 22px; }
.hint { color: #94a3b8; font-size: 12px; margin-top: 18px; line-height: 1.6; }
@media (max-width: 720px) {
  .login-card { grid-template-columns: 1fr; }
  .hero { padding: 32px 24px; }
  .login-form { padding: 28px 24px; }
}
</style>
