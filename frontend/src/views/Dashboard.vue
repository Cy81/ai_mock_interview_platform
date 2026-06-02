<script setup>
/**
 * 客户端工作台：
 *  - 顶部 4 个核心 KPI；
 *  - 中部"业务链路 + 最新雷达图报告"；
 *  - 底部岗位池快照。
 *  返回值适配后端 Page[T]：{ items, total, page, page_size }。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { ArrowRight, RefreshCw, Sparkles, Trophy } from 'lucide-vue-next'
import { interviewApi, jobApi, resumeApi } from '@/api/modules'

const router = useRouter()

const loading = ref(false)
const error = ref('')
const resumes = ref([])
const interviews = ref([])
const jobs = ref([])

const completed = computed(
  () => interviews.value.filter((i) => i.status === 'completed').length,
)
const inProgress = computed(
  () => interviews.value.filter((i) => i.status === 'in_progress').length,
)
const latestReport = computed(() => {
  const completedItems = interviews.value
    .filter((i) => i.status === 'completed' && i.score_report)
    .sort((a, b) => new Date(b.completed_at || 0) - new Date(a.completed_at || 0))
  return completedItems[0]?.score_report || null
})

const radarOption = computed(() => {
  const dim = latestReport.value?.dimension_scores
  if (!dim) return null
  const indicator = Object.keys(dim).map((name) => ({ name, max: 100 }))
  return {
    radar: {
      indicator,
      splitLine: { lineStyle: { color: '#cbd5e1' } },
      splitArea: { areaStyle: { color: ['#f8fafc', '#f1f5f9'] } },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      name: { textStyle: { color: '#475569', fontSize: 12 } },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: Object.values(dim),
            name: '当前评分',
            areaStyle: { color: 'rgba(59,130,246,.18)' },
            lineStyle: { color: '#3b82f6', width: 2 },
            itemStyle: { color: '#3b82f6' },
          },
        ],
      },
    ],
    tooltip: { trigger: 'item' },
  }
})

const trendOption = computed(() => {
  const completedItems = interviews.value
    .filter((i) => i.status === 'completed' && i.score_report)
    .sort((a, b) => new Date(a.completed_at || 0) - new Date(b.completed_at || 0))
    .slice(-8)
  if (!completedItems.length) return null
  return {
    grid: { left: 30, right: 14, top: 24, bottom: 28 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: completedItems.map(
        (i, idx) => `#${i.id || idx + 1}`,
      ),
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: '#e2e8f0' } },
      axisLabel: { color: '#64748b', fontSize: 11 },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbolSize: 8,
        lineStyle: { color: '#8b5cf6', width: 2.5 },
        itemStyle: { color: '#8b5cf6' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(139,92,246,.4)' },
              { offset: 1, color: 'rgba(139,92,246,0)' },
            ],
          },
        },
        data: completedItems.map((i) => i.score_report?.overall_score || 0),
      },
    ],
  }
})

function unwrap(resp) {
  if (Array.isArray(resp)) return resp
  if (resp && Array.isArray(resp.items)) return resp.items
  return []
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [resumeData, interviewData, jobData] = await Promise.all([
      resumeApi.list({ page: 1, page_size: 50 }),
      interviewApi.list({ page: 1, page_size: 50 }),
      jobApi.list(),
    ])
    resumes.value = unwrap(resumeData)
    interviews.value = unwrap(interviewData)
    jobs.value = unwrap(jobData)
  } catch (err) {
    error.value = err?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="dashboard">
    <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />

    <el-row :gutter="16" class="kpis">
      <el-col :xs="12" :md="6">
        <el-card shadow="hover" class="kpi kpi-blue">
          <span>简历档案</span>
          <strong>{{ resumes.length }}</strong>
          <small>覆盖原始 + 解析版本</small>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="hover" class="kpi kpi-amber">
          <span>面试总场次</span>
          <strong>{{ interviews.length }}</strong>
          <small>含进行中 / 已完成 / 已取消</small>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="hover" class="kpi kpi-emerald">
          <span>已出报告</span>
          <strong>{{ completed }}</strong>
          <small>含双 RAG 引用 / 学习计划</small>
        </el-card>
      </el-col>
      <el-col :xs="12" :md="6">
        <el-card shadow="hover" class="kpi kpi-violet">
          <span>进行中</span>
          <strong>{{ inProgress }}</strong>
          <small>待回答 / 待评分</small>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt">
      <el-col :xs="24" :md="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <h3>评分趋势</h3>
              <el-button text :icon="RefreshCw" :loading="loading" @click="load">刷新</el-button>
            </div>
          </template>
          <div v-if="trendOption" class="chart-wrap">
            <VChart :option="trendOption" autoresize style="height: 280px" />
          </div>
          <el-empty v-else description="尚未生成评分报告" />
        </el-card>
      </el-col>

      <el-col :xs="24" :md="10">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <h3>最新评估雷达</h3>
              <el-tag v-if="latestReport" size="small" type="success">
                <Trophy :size="12" /> {{ latestReport.level }} · {{ latestReport.overall_score }}
              </el-tag>
            </div>
          </template>
          <div v-if="radarOption" class="chart-wrap">
            <VChart :option="radarOption" autoresize style="height: 280px" />
          </div>
          <el-empty v-else description="完成一场面试以查看雷达图" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mt">
      <template #header>
        <div class="card-head">
          <h3>岗位池</h3>
          <el-button text type="primary" @click="router.push('/jobs')">
            进入推荐 Agent <ArrowRight :size="14" />
          </el-button>
        </div>
      </template>
      <el-empty v-if="!jobs.length" description="岗位池暂无数据" />
      <el-row v-else :gutter="14">
        <el-col v-for="job in jobs.slice(0, 6)" :key="job.code" :xs="24" :md="8" class="job-col">
          <div class="job-card">
            <div class="job-head">
              <strong>{{ job.title }}</strong>
              <el-tag size="small" effect="plain">{{ job.code }}</el-tag>
            </div>
            <p class="muted">{{ job.description || '暂无描述' }}</p>
            <div class="tags">
              <el-tag
                v-for="skill in (job.required_skills || []).slice(0, 5)"
                :key="skill"
                size="small"
                type="info"
                effect="plain"
              >
                {{ skill }}
              </el-tag>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="mt cta">
      <Sparkles :size="20" />
      <div>
        <strong>下一步建议</strong>
        <p>上传简历 → 让岗位 Agent 推荐方向 → 选取岗位发起模拟面试 → 查看双 RAG 加持的评分报告。</p>
      </div>
      <el-button type="primary" @click="router.push('/resumes')">立即开始</el-button>
    </el-card>
  </div>
</template>

<style scoped>
.dashboard { display: flex; flex-direction: column; gap: 16px; }
.mt { margin-top: 4px; }
.kpis :deep(.el-card__body) { padding: 18px 20px; }
.kpi { border: 0; border-radius: 14px; color: #fff; min-height: 110px; }
.kpi span { font-size: 12px; letter-spacing: 1px; opacity: .9; }
.kpi strong { display: block; font-size: 30px; margin: 6px 0 4px; }
.kpi small { font-size: 11px; opacity: .8; }
.kpi-blue { background: linear-gradient(135deg,#0ea5e9,#3b82f6); }
.kpi-amber { background: linear-gradient(135deg,#f59e0b,#f97316); }
.kpi-emerald { background: linear-gradient(135deg,#10b981,#22c55e); }
.kpi-violet { background: linear-gradient(135deg,#8b5cf6,#6366f1); }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-head h3 { margin: 0; font-size: 15px; color: #0f172a; }
.chart-wrap { height: 280px; }
.job-col { margin-bottom: 12px; }
.job-card {
  background: #f8fafc; border-radius: 12px; padding: 14px 16px; height: 100%;
  border: 1px solid #e2e8f0; display: flex; flex-direction: column; gap: 8px;
}
.job-head { display: flex; justify-content: space-between; align-items: center; }
.muted { color: #64748b; font-size: 12px; line-height: 1.6; margin: 0; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.cta {
  display: flex; align-items: center; gap: 16px;
  background: linear-gradient(120deg,#eff6ff,#f5f3ff);
  border: 1px dashed #c7d2fe;
}
.cta :deep(.el-card__body) { display: flex; align-items: center; gap: 18px; width: 100%; }
.cta strong { color: #1e293b; }
.cta p { color: #475569; margin: 4px 0 0; font-size: 13px; }
</style>
