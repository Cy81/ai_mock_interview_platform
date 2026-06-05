<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CheckCircle2, RotateCw, Save, ShieldCheck, SlidersHorizontal } from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const apiKeyDirty = ref(false)
const current = ref(null)
const testResult = ref(null)

const form = reactive({
  name: 'Local Mock',
  runtime: 'mock',
  provider: 'mock',
  base_url: '',
  api_key: '',
  model: 'mock-interview',
  temperature: 0.2,
  max_tokens: 2048,
  timeout: 60,
  max_retries: 3,
})

const statusType = computed(() => {
  const status = current.value?.last_test_status || testResult.value?.status
  if (status === 'ok') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
})

const statusText = computed(() => {
  const status = current.value?.last_test_status || testResult.value?.status
  if (status === 'ok') return '连接正常'
  if (status === 'failed') return '连接失败'
  return '未测试'
})

watch(
  () => form.runtime,
  (runtime) => {
    if (runtime === 'mock') {
      form.provider = 'mock'
      form.base_url = ''
      if (!form.model || form.model === 'deepseek-chat') form.model = 'mock-interview'
    } else {
      form.provider = 'deepseek'
      if (!form.base_url) form.base_url = 'https://api.deepseek.com'
      if (!form.model || form.model === 'mock-interview') form.model = 'deepseek-chat'
    }
  },
)

function assignForm(payload) {
  current.value = payload
  form.name = payload.name || 'Local Mock'
  form.runtime = payload.runtime || 'mock'
  form.provider = payload.provider || 'mock'
  form.base_url = payload.base_url || ''
  form.api_key = ''
  form.model = payload.model || 'mock-interview'
  form.temperature = payload.temperature ?? 0.2
  form.max_tokens = payload.max_tokens ?? 2048
  form.timeout = payload.timeout ?? 60
  form.max_retries = payload.max_retries ?? 3
  apiKeyDirty.value = false
}

async function load() {
  loading.value = true
  try {
    assignForm(await adminApi.getAiConfig())
  } catch (err) {
    ElMessage.error(err?.message || '加载模型配置失败')
  } finally {
    loading.value = false
  }
}

function buildPayload() {
  return {
    name: form.name.trim(),
    runtime: form.runtime,
    provider: form.provider,
    base_url: form.base_url.trim(),
    api_key: apiKeyDirty.value ? form.api_key.trim() : null,
    model: form.model.trim(),
    temperature: Number(form.temperature),
    max_tokens: Number(form.max_tokens),
    timeout: Number(form.timeout),
    max_retries: Number(form.max_retries),
  }
}

async function save() {
  saving.value = true
  try {
    assignForm(await adminApi.updateAiConfig(buildPayload()))
    ElMessage.success('模型配置已保存')
  } catch (err) {
    ElMessage.error(err?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function runTest() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await adminApi.testAiConfig()
    await load()
    if (testResult.value.ok) {
      ElMessage.success('模型连接测试通过')
    } else {
      ElMessage.error(testResult.value.error || '模型连接测试失败')
    }
  } catch (err) {
    ElMessage.error(err?.message || '测试失败')
  } finally {
    testing.value = false
  }
}

function clearApiKey() {
  form.api_key = ''
  apiKeyDirty.value = true
}

onMounted(load)
</script>

<template>
  <div class="ai-config-admin" v-loading="loading">
    <section class="admin-section hero-section">
      <div>
        <p class="eyebrow">AI RUNTIME</p>
        <h2><SlidersHorizontal :size="22" /> 模型配置</h2>
        <p class="subtle">配置面试 Agent 使用的大模型参数，保存后新请求会读取当前活动配置。</p>
      </div>
      <el-tag :type="statusType" size="large">{{ statusText }}</el-tag>
    </section>

    <section class="config-grid">
      <form class="admin-section config-form" @submit.prevent="save">
        <div class="section-title">
          <div>
            <p class="eyebrow">ACTIVE PROFILE</p>
            <h3>活动模型档案</h3>
          </div>
          <el-button type="primary" :loading="saving" @click="save">
            <Save :size="16" />
            保存配置
          </el-button>
        </div>

        <el-form label-position="top">
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="配置名称">
                <el-input v-model="form.name" maxlength="120" />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="运行模式">
                <el-select v-model="form.runtime" style="width: 100%">
                  <el-option label="Mock 本地模式" value="mock" />
                  <el-option label="DeepSeek" value="deepseek" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="Provider">
                <el-select v-model="form.provider" style="width: 100%">
                  <el-option label="Mock" value="mock" />
                  <el-option label="DeepSeek" value="deepseek" />
                </el-select>
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item label="API URL">
            <el-input
              v-model="form.base_url"
              class="base-url-field"
              placeholder="https://api.deepseek.com"
              :disabled="form.runtime === 'mock'"
            />
          </el-form-item>

          <el-form-item label="API Key">
            <div class="secret-field">
              <el-input
                v-model="form.api_key"
                type="password"
                show-password
                autocomplete="new-password"
                :placeholder="current?.has_api_key ? `已保存：${current.api_key_masked}` : '输入 API Key'"
                :disabled="form.runtime === 'mock'"
                @input="apiKeyDirty = true"
              />
              <el-button :disabled="form.runtime === 'mock' || !current?.has_api_key" @click="clearApiKey">
                清除密钥
              </el-button>
            </div>
          </el-form-item>

          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="模型名称">
                <el-input v-model="form.model" maxlength="120" />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="Temperature">
                <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.05" />
              </el-form-item>
            </el-col>
            <el-col :span="6">
              <el-form-item label="Max Tokens">
                <el-input-number v-model="form.max_tokens" :min="1" :max="128000" :step="256" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="超时时间（秒）">
                <el-input-number v-model="form.timeout" :min="1" :max="600" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="最大重试次数">
                <el-input-number v-model="form.max_retries" :min="0" :max="10" />
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>
      </form>

      <aside class="admin-section model-connection-test">
        <div class="section-title compact">
          <div>
            <p class="eyebrow">CONNECTION</p>
            <h3>可用性测试</h3>
          </div>
          <ShieldCheck :size="20" />
        </div>

        <dl class="status-list">
          <div>
            <dt>当前模式</dt>
            <dd>{{ current?.runtime || '-' }}</dd>
          </div>
          <div>
            <dt>模型</dt>
            <dd>{{ current?.model || '-' }}</dd>
          </div>
          <div>
            <dt>密钥状态</dt>
            <dd>{{ current?.has_api_key ? current.api_key_masked : '未配置' }}</dd>
          </div>
          <div>
            <dt>最近测试</dt>
            <dd>
              <el-tag :type="statusType">{{ statusText }}</el-tag>
            </dd>
          </div>
          <div>
            <dt>耗时</dt>
            <dd>{{ current?.last_test_latency_ms ?? testResult?.latency_ms ?? '-' }} ms</dd>
          </div>
        </dl>

        <el-alert
          v-if="current?.last_test_error || testResult?.error"
          class="test-error"
          type="error"
          :closable="false"
          show-icon
          :title="current?.last_test_error || testResult?.error"
        />

        <el-button class="test-button" type="success" :loading="testing" @click="runTest">
          <RotateCw :size="16" />
          测试可用性
        </el-button>

        <p class="test-note">
          Mock 模式会本地通过；DeepSeek 模式会向配置的 OpenAI Compatible 地址发起一次短请求。
        </p>
      </aside>
    </section>

    <section class="admin-section runtime-panel">
      <CheckCircle2 :size="18" />
      <span>当前配置会被 LangChain 面试 Agent 读取；简历解析 Provider 暂时仍保留环境变量兜底。</span>
    </section>
  </div>
</template>

<style scoped>
.ai-config-admin {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-section {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 18px;
}

.hero-section,
.section-title,
.runtime-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.hero-section h2,
.section-title h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: #0f172a;
}

.eyebrow {
  margin: 0 0 4px;
  color: #64748b;
  font-size: 11px;
  letter-spacing: 1.5px;
}

.subtle,
.test-note {
  color: #64748b;
  margin: 6px 0 0;
  line-height: 1.6;
}

.config-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: start;
}

.config-form {
  min-width: 0;
}

.compact {
  align-items: flex-start;
}

.secret-field {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  width: 100%;
}

.status-list {
  display: grid;
  gap: 12px;
  margin: 18px 0;
}

.status-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 10px;
}

.status-list dt {
  color: #64748b;
}

.status-list dd {
  margin: 0;
  color: #0f172a;
  font-weight: 600;
  text-align: right;
  word-break: break-all;
}

.test-error {
  margin-bottom: 12px;
}

.test-button {
  width: 100%;
}

.test-button :deep(span),
.section-title :deep(.el-button span) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.runtime-panel {
  justify-content: flex-start;
  color: #475569;
}

@media (max-width: 1080px) {
  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
