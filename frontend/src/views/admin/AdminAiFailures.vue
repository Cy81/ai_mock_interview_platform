<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Activity,
  AlertTriangle,
  Clock3,
  RefreshCw,
  ServerCrash,
} from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const loading = ref(false)
const overview = ref({
  total_ai_calls: 0,
  failed_ai_calls: 0,
  failed_interviews: 0,
  failure_rate: 0,
  recent_ai_failures: [],
  recent_failed_interviews: [],
})
const filters = reactive({
  days: 7,
  limit: 20,
})

const hasFailures = computed(
  () => overview.value.failed_ai_calls > 0 || overview.value.failed_interviews > 0,
)

async function loadOverview() {
  loading.value = true
  try {
    overview.value = await adminApi.getAiFailureOverview({
      days: filters.days,
      limit: filters.limit,
    })
  } catch (err) {
    ElMessage.error(err?.message || '加载异常监控失败')
  } finally {
    loading.value = false
  }
}

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

onMounted(loadOverview)
</script>

<template>
  <div class="ai-failures-admin">
    <section class="admin-section hero-section">
      <div>
        <p class="eyebrow">FAILURE MONITORING</p>
        <h2><AlertTriangle :size="22" /> 异常监控</h2>
        <p class="subtle">集中查看 AI 调用失败、异常信息和失败面试，方便快速定位问题。</p>
      </div>
      <div class="hero-actions">
        <el-select v-model="filters.days" style="width: 130px" @change="loadOverview">
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 30 天" :value="30" />
          <el-option label="近 90 天" :value="90" />
        </el-select>
        <el-button :loading="loading" @click="loadOverview">
          <RefreshCw :size="16" />
          刷新
        </el-button>
      </div>
    </section>

    <section class="failure-summary-grid">
      <article class="metric-card">
        <Activity :size="18" />
        <span>AI 调用总数</span>
        <strong>{{ overview.total_ai_calls }}</strong>
      </article>
      <article class="metric-card danger">
        <ServerCrash :size="18" />
        <span>失败调用</span>
        <strong>{{ overview.failed_ai_calls }}</strong>
      </article>
      <article class="metric-card danger">
        <AlertTriangle :size="18" />
        <span>失败面试</span>
        <strong>{{ overview.failed_interviews }}</strong>
      </article>
      <article class="metric-card">
        <Clock3 :size="18" />
        <span>失败率</span>
        <strong>{{ overview.failure_rate }}%</strong>
      </article>
    </section>

    <el-alert
      v-if="!hasFailures && !loading"
      type="success"
      show-icon
      :closable="false"
      title="当前时间范围内没有失败调用或失败面试"
    />

    <section class="admin-section failed-ai-log-table">
      <div class="section-title">
        <div>
          <p class="eyebrow">FAILED AI CALLS</p>
          <h3>失败调用</h3>
        </div>
      </div>
      <el-table v-loading="loading" :data="overview.recent_ai_failures" border>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="feature" label="功能" width="140" />
        <el-table-column prop="provider" label="Provider" width="110" />
        <el-table-column prop="model" label="模型" min-width="160" show-overflow-tooltip />
        <el-table-column prop="latency_ms" label="延迟 ms" width="110" />
        <el-table-column prop="request_id" label="Request ID" min-width="150" show-overflow-tooltip />
        <el-table-column prop="error" label="异常" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error || '-' }}</template>
        </el-table-column>
      </el-table>
    </section>

    <section class="admin-section failed-interview-table">
      <div class="section-title">
        <div>
          <p class="eyebrow">FAILED INTERVIEWS</p>
          <h3>失败面试</h3>
        </div>
      </div>
      <el-table v-loading="loading" :data="overview.recent_failed_interviews" border>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="user_id" label="用户 ID" width="100" />
        <el-table-column prop="job_title" label="岗位" min-width="160" show-overflow-tooltip />
        <el-table-column prop="status_reason" label="失败原因" min-width="260" show-overflow-tooltip>
          <template #default="{ row }">{{ row.status_reason || '-' }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.ai-failures-admin {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-section,
.metric-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 18px;
}

.hero-section,
.section-title,
.hero-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hero-section h2,
.section-title h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: #0f172a;
}

.hero-actions :deep(.el-button span) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.eyebrow {
  margin: 0 0 4px;
  color: #64748b;
  font-size: 11px;
  letter-spacing: 1.5px;
}

.subtle {
  margin: 6px 0 0;
  color: #64748b;
}

.failure-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.metric-card {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 10px;
  align-items: center;
}

.metric-card svg {
  color: #2563eb;
}

.metric-card.danger svg {
  color: #dc2626;
}

.metric-card span {
  color: #64748b;
}

.metric-card strong {
  grid-column: 1 / -1;
  color: #0f172a;
  font-size: 26px;
}

.section-title {
  margin-bottom: 14px;
}

@media (max-width: 1080px) {
  .failure-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .hero-section {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
