<script setup>
/**
 * 评分报告：
 *  - 左侧：已完成面试列表（仅 status=completed）；
 *  - 右侧：选中报告——雷达图、维度对比横条、优势/改进/学习计划、逐题反馈、面试官原话；
 *  - 报告通过 reports/{id} 单独取，错误（如还在评分中）会被全局拦截器提示。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import VChart from 'vue-echarts'
import { ElMessage } from 'element-plus'
import {
  Award,
  ClipboardList,
  Download,
  FileCheck2,
  RefreshCw,
  Sparkles,
} from 'lucide-vue-next'
import { interviewApi, reportApi } from '@/api/modules'

const route = useRoute()
const router = useRouter()

const interviews = ref([])
const loading = ref(false)
const reportLoading = ref(false)
const detail = ref(null)
const activeId = ref(null)

const completedList = computed(() =>
  interviews.value.filter((i) => i.status === 'completed'),
)

function unwrap(resp) {
  if (Array.isArray(resp)) return resp
  if (resp && Array.isArray(resp.items)) return resp.items
  return []
}

async function loadList() {
  loading.value = true
  try {
    const resp = await interviewApi.list({ page: 1, page_size: 50 })
    interviews.value = unwrap(resp)
    if (!activeId.value && completedList.value.length) {
      const target =
        Number(route.params.id) ||
        Number(route.query.id) ||
        completedList.value[0].id
      await pick(target)
    }
  } catch (err) {
    ElMessage.error(err?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function pick(id) {
  if (!id) return
  activeId.value = id
  reportLoading.value = true
  try {
    detail.value = await reportApi.get(id)
  } catch (err) {
    detail.value = null
    ElMessage.error(err?.message || '报告还没准备好')
  } finally {
    reportLoading.value = false
  }
}

const reportBody = computed(() => detail.value?.report || null)

const radarOption = computed(() => {
  const dim = reportBody.value?.dimension_scores
  if (!dim) return null
  const keys = Object.keys(dim)
  return {
    radar: {
      indicator: keys.map((name) => ({ name, max: 100 })),
      splitArea: { areaStyle: { color: ['#f8fafc', '#f1f5f9'] } },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      splitLine: { lineStyle: { color: '#cbd5e1' } },
      name: { textStyle: { color: '#475569', fontSize: 12 } },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: keys.map((k) => dim[k]),
            name: '维度评分',
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

const barOption = computed(() => {
  const dim = reportBody.value?.dimension_scores
  if (!dim) return null
  const keys = Object.keys(dim)
  return {
    grid: { left: 110, right: 24, top: 10, bottom: 24 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'value',
      max: 100,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      splitLine: { lineStyle: { color: '#e2e8f0' } },
    },
    yAxis: {
      type: 'category',
      data: keys,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#475569', fontSize: 12 },
    },
    series: [
      {
        type: 'bar',
        data: keys.map((k) => dim[k]),
        barWidth: 16,
        itemStyle: {
          borderRadius: [0, 8, 8, 0],
          color: {
            type: 'linear',
            x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: '#60a5fa' },
              { offset: 1, color: '#8b5cf6' },
            ],
          },
        },
        label: { show: true, position: 'right', color: '#0f172a', fontSize: 12 },
      },
    ],
  }
})

function exportReport() {
  if (!detail.value) return
  const text = JSON.stringify(detail.value, null, 2)
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `interview_${detail.value.interview_id}_report.json`
  a.click()
  URL.revokeObjectURL(url)
}

watch(
  () => route.params.id,
  (id) => {
    if (id && Number(id) !== activeId.value) pick(Number(id))
  },
)

onMounted(loadList)
</script>

<template>
  <div class="reports-page">
    <div class="layout">
      <aside class="aside">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <h3><FileCheck2 :size="16" /> 已完成面试</h3>
              <el-button text :icon="RefreshCw" :loading="loading" @click="loadList" />
            </div>
          </template>
          <el-skeleton v-if="loading" :rows="5" animated />
          <el-empty
            v-else-if="!completedList.length"
            description="尚无已完成面试"
            :image-size="80"
          >
            <el-button type="primary" @click="router.push('/interviews')">去面试</el-button>
          </el-empty>
          <ul v-else class="report-list">
            <li
              v-for="item in completedList"
              :key="item.id"
              :class="{ active: activeId === item.id }"
              @click="pick(item.id)"
            >
              <div class="row">
                <strong>#{{ item.id }} {{ item.job_title }}</strong>
                <el-tag size="small" type="success">{{ item.overall_score ?? '—' }}</el-tag>
              </div>
              <small class="muted">
                {{ new Date(item.completed_at || item.created_at).toLocaleString() }}
              </small>
            </li>
          </ul>
        </el-card>
      </aside>

      <main class="detail">
        <el-skeleton v-if="reportLoading" :rows="10" animated />

        <el-empty
          v-else-if="!detail || !reportBody"
          description="选择一份已完成面试以查看报告"
        />

        <template v-else>
          <el-card shadow="never" class="hero-card">
            <div class="hero">
              <div>
                <p class="eyebrow">REPORT · #{{ detail.interview_id }}</p>
                <h2>{{ detail.job_title }}</h2>
                <p class="muted">
                  完成于 {{ new Date(detail.completed_at).toLocaleString() }}
                </p>
              </div>
              <div class="hero-score">
                <Award :size="28" />
                <strong>{{ detail.overall_score ?? '—' }}</strong>
                <small>{{ reportBody.level || '综合评分' }}</small>
              </div>
              <el-button type="primary" plain :icon="Download" @click="exportReport">
                导出 JSON
              </el-button>
            </div>
          </el-card>

          <el-row :gutter="16" class="mt">
            <el-col :xs="24" :md="10">
              <el-card shadow="never">
                <template #header>
                  <div class="card-head"><h3>能力雷达</h3></div>
                </template>
                <VChart v-if="radarOption" :option="radarOption" autoresize style="height: 300px" />
                <el-empty v-else description="无维度数据" :image-size="80" />
              </el-card>
            </el-col>
            <el-col :xs="24" :md="14">
              <el-card shadow="never">
                <template #header>
                  <div class="card-head"><h3>维度得分对比</h3></div>
                </template>
                <VChart v-if="barOption" :option="barOption" autoresize style="height: 300px" />
                <el-empty v-else description="无维度数据" :image-size="80" />
              </el-card>
            </el-col>
          </el-row>

          <el-row :gutter="16" class="mt">
            <el-col :xs="24" :md="8">
              <el-card shadow="never">
                <template #header><div class="card-head"><h3>优势</h3></div></template>
                <ul class="bullets">
                  <li v-for="s in reportBody.strengths || []" :key="s">{{ s }}</li>
                  <li v-if="!reportBody.strengths?.length" class="muted">未提取到亮点</li>
                </ul>
              </el-card>
            </el-col>
            <el-col :xs="24" :md="8">
              <el-card shadow="never">
                <template #header><div class="card-head"><h3>改进建议</h3></div></template>
                <ul class="bullets warn">
                  <li v-for="i in reportBody.improvements || []" :key="i">{{ i }}</li>
                  <li v-if="!reportBody.improvements?.length" class="muted">无明显改进点</li>
                </ul>
              </el-card>
            </el-col>
            <el-col :xs="24" :md="8">
              <el-card shadow="never">
                <template #header>
                  <div class="card-head"><h3><Sparkles :size="14" /> 学习计划</h3></div>
                </template>
                <ol class="bullets">
                  <li v-for="step in reportBody.learning_plan || []" :key="step">{{ step }}</li>
                  <li v-if="!reportBody.learning_plan?.length" class="muted">暂无</li>
                </ol>
              </el-card>
            </el-col>
          </el-row>

          <el-card shadow="never" class="mt">
            <template #header>
              <div class="card-head">
                <h3><ClipboardList :size="14" /> 逐题反馈</h3>
                <span class="muted">{{ (reportBody.question_scores || []).length }} 题</span>
              </div>
            </template>
            <el-empty
              v-if="!(reportBody.question_scores || []).length"
              description="无逐题数据"
              :image-size="80"
            />
            <el-collapse v-else>
              <el-collapse-item
                v-for="q in reportBody.question_scores"
                :key="q.question_id"
                :name="q.question_id"
              >
                <template #title>
                  <div class="q-title">
                    <el-tag size="small" :type="q.score >= 75 ? 'success' : q.score >= 60 ? 'warning' : 'danger'">
                      {{ q.score ?? '—' }}
                    </el-tag>
                    <span>{{ q.question }}</span>
                  </div>
                </template>
                <p class="muted q-comment">{{ q.comment || '暂无评语' }}</p>
                <p v-if="q.candidate_answer" class="answer-quote">
                  <strong>候选人答：</strong>{{ q.candidate_answer }}
                </p>
              </el-collapse-item>
            </el-collapse>
          </el-card>

          <el-card v-if="reportBody.interviewer_remark" shadow="never" class="mt remark">
            <strong>面试官总评</strong>
            <p>{{ reportBody.interviewer_remark }}</p>
          </el-card>
        </template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.reports-page { display: flex; flex-direction: column; }
.layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; align-items: flex-start; }
.aside { position: sticky; top: 12px; }
.detail { display: flex; flex-direction: column; gap: 14px; }
.mt { margin-top: 4px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-head h3 { margin: 0; font-size: 14px; color: #0f172a; display: flex; align-items: center; gap: 6px; }
.muted { color: #94a3b8; font-size: 12px; }
.report-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
.report-list li {
  border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; cursor: pointer;
  background: #fff; transition: all .15s;
}
.report-list li:hover { border-color: #93c5fd; }
.report-list li.active { border-color: #3b82f6; background: #eff6ff; }
.report-list .row { display: flex; justify-content: space-between; align-items: center; }
.report-list strong { color: #0f172a; font-size: 13px; }
.hero-card { background: linear-gradient(120deg,#eff6ff,#f5f3ff); border: 0; }
.hero { display: flex; align-items: center; gap: 18px; }
.hero .eyebrow { margin: 0; font-size: 11px; color: #94a3b8; letter-spacing: 1.5px; }
.hero h2 { margin: 4px 0 4px; color: #0f172a; font-size: 22px; }
.hero-score {
  margin-left: auto; display: flex; flex-direction: column; align-items: center;
  background: #fff; padding: 12px 20px; border-radius: 14px;
  box-shadow: 0 4px 18px -10px rgba(15,23,42,.2);
}
.hero-score strong { font-size: 36px; color: #0f172a; line-height: 1; margin: 4px 0; }
.hero-score small { color: #64748b; font-size: 11px; letter-spacing: 1px; }
.bullets { padding-left: 20px; margin: 0; color: #1e293b; }
.bullets li { line-height: 1.8; font-size: 13px; }
.bullets.warn li { color: #b45309; }
.q-title { display: flex; align-items: center; gap: 10px; flex: 1; }
.q-comment { color: #475569; font-size: 13px; line-height: 1.7; margin: 0; }
.answer-quote {
  margin-top: 8px; padding: 10px 12px; background: #f8fafc;
  border-left: 3px solid #cbd5e1; border-radius: 0 6px 6px 0;
  color: #334155; font-size: 12px; line-height: 1.7;
}
.remark { background: #fffbeb; border: 1px solid #fde68a; }
.remark strong { color: #92400e; }
.remark p { margin: 6px 0 0; color: #78350f; line-height: 1.7; }
@media (max-width: 1024px) {
  .layout { grid-template-columns: 1fr; }
  .aside { position: static; }
}
</style>
