<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Activity, BarChart3, Clock3, Coins, RefreshCw, TriangleAlert } from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const loading = ref(false)
const logsLoading = ref(false)
const summary = ref({
  total_calls: 0,
  success_calls: 0,
  failed_calls: 0,
  total_tokens: 0,
  prompt_tokens: 0,
  completion_tokens: 0,
  avg_latency_ms: 0,
  by_model: [],
})
const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filters = reactive({
  days: 7,
  feature: '',
  status: '',
})

const successRate = computed(() => {
  if (!summary.value.total_calls) return '0%'
  return `${Math.round((summary.value.success_calls / summary.value.total_calls) * 100)}%`
})

function unwrap(resp) {
  return Array.isArray(resp?.items) ? resp.items : []
}

async function loadSummary() {
  loading.value = true
  try {
    summary.value = await adminApi.getAiUsageSummary({ days: filters.days })
  } catch (err) {
    ElMessage.error(err?.message || '加载用量汇总失败')
  } finally {
    loading.value = false
  }
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const params = {
      page: page.value,
      page_size: pageSize.value,
      feature: filters.feature || undefined,
      status: filters.status || undefined,
    }
    const resp = await adminApi.listAiUsage(params)
    logs.value = unwrap(resp)
    total.value = resp.total || 0
  } catch (err) {
    ElMessage.error(err?.message || '加载调用日志失败')
  } finally {
    logsLoading.value = false
  }
}

function reload() {
  loadSummary()
  loadLogs()
}

function onFilter() {
  page.value = 1
  loadLogs()
}

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function statusType(status) {
  return status === 'ok' ? 'success' : 'danger'
}

onMounted(reload)
</script>

<template>
  <div class="ai-usage-admin">
    <section class="admin-section hero-section">
      <div>
        <p class="eyebrow">OBSERVABILITY</p>
        <h2><BarChart3 :size="22" /> 用量观测</h2>
        <p class="subtle">查看大模型调用次数、Token 消耗、延迟和失败情况。</p>
      </div>
      <div class="hero-actions">
        <el-select v-model="filters.days" style="width: 130px" @change="loadSummary">
          <el-option label="近 7 天" :value="7" />
          <el-option label="近 30 天" :value="30" />
          <el-option label="近 90 天" :value="90" />
        </el-select>
        <el-button :loading="loading || logsLoading" @click="reload">
          <RefreshCw :size="16" />
          刷新
        </el-button>
      </div>
    </section>

    <section class="usage-summary-grid">
      <article class="metric-card">
        <Activity :size="18" />
        <span>调用次数</span>
        <strong>{{ summary.total_calls }}</strong>
      </article>
      <article class="metric-card">
        <Coins :size="18" />
        <span>Token 总量</span>
        <strong>{{ summary.total_tokens }}</strong>
      </article>
      <article class="metric-card">
        <Clock3 :size="18" />
        <span>平均延迟</span>
        <strong>{{ summary.avg_latency_ms }} ms</strong>
      </article>
      <article class="metric-card">
        <TriangleAlert :size="18" />
        <span>成功率</span>
        <strong>{{ successRate }}</strong>
      </article>
    </section>

    <section class="admin-section model-usage-table">
      <div class="section-title">
        <div>
          <p class="eyebrow">MODEL BREAKDOWN</p>
          <h3>按模型聚合</h3>
        </div>
      </div>
      <el-table :data="summary.by_model" border>
        <el-table-column prop="model" label="模型" min-width="180" />
        <el-table-column prop="runtime" label="Runtime" width="120" />
        <el-table-column prop="provider" label="Provider" width="120" />
        <el-table-column prop="calls" label="调用" width="100" />
        <el-table-column prop="total_tokens" label="Tokens" width="120" />
        <el-table-column prop="avg_latency_ms" label="平均延迟 ms" width="140" />
        <el-table-column prop="failed_calls" label="失败" width="100" />
      </el-table>
    </section>

    <section class="admin-section usage-log-table">
      <div class="section-title table-title">
        <div>
          <p class="eyebrow">CALL LOGS</p>
          <h3>最近调用</h3>
        </div>
        <div class="filters">
          <el-input
            v-model="filters.feature"
            placeholder="feature，如 config_test"
            clearable
            style="width: 220px"
            @change="onFilter"
            @clear="onFilter"
          />
          <el-select v-model="filters.status" clearable placeholder="状态" style="width: 130px" @change="onFilter">
            <el-option label="成功" value="ok" />
            <el-option label="失败" value="failed" />
          </el-select>
        </div>
      </div>

      <el-table v-loading="logsLoading" :data="logs" border>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="feature" label="功能" width="140" />
        <el-table-column prop="model" label="模型" min-width="160" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="Tokens" width="110" />
        <el-table-column prop="latency_ms" label="延迟 ms" width="110" />
        <el-table-column prop="error" label="异常" min-width="180">
          <template #default="{ row }">{{ row.error || '-' }}</template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        style="margin-top: 14px; justify-content: flex-end"
        @current-change="loadLogs"
        @size-change="loadLogs"
      />
    </section>
  </div>
</template>

<style scoped>
.ai-usage-admin {
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
.hero-actions,
.filters {
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

.usage-summary-grid {
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

.metric-card span {
  color: #64748b;
}

.metric-card strong {
  grid-column: 1 / -1;
  color: #0f172a;
  font-size: 26px;
}

.table-title {
  margin-bottom: 14px;
}

@media (max-width: 1080px) {
  .usage-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .hero-section,
  .table-title {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
