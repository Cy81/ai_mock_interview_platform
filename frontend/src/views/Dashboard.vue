<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowRight,
  Briefcase,
  Clock3,
  FileText,
  Play,
  RefreshCw,
  Sparkles,
  Upload,
} from 'lucide-vue-next'
import { interviewApi, jobApi, resumeApi } from '@/api/modules'

const router = useRouter()

const loading = ref(false)
const error = ref('')
const resumes = ref([])
const interviews = ref([])
const jobs = ref([])
const selectedResumeId = ref('')
const selectedJobCode = ref('')

const statusMeta = {
  created: { type: 'info', label: '已创建' },
  generating: { type: 'warning', label: '生成中' },
  in_progress: { type: 'primary', label: '进行中' },
  scoring: { type: 'warning', label: '评分中' },
  completed: { type: 'success', label: '已完成' },
  failed: { type: 'danger', label: '失败' },
  cancelled: { type: 'info', label: '已取消' },
}

const parsedResumes = computed(() =>
  resumes.value.filter((item) => item.parse_status === 'parsed'),
)
const latestInterviews = computed(() =>
  [...interviews.value].sort(
    (a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0),
  ),
)
const completedCount = computed(
  () => interviews.value.filter((item) => item.status === 'completed').length,
)
const activeCount = computed(
  () => interviews.value.filter((item) => ['created', 'in_progress', 'scoring'].includes(item.status)).length,
)
const latestScore = computed(() => {
  const report = latestInterviews.value.find((item) => item.score_report)?.score_report
  return report?.overall_score ? Math.round(report.overall_score) : null
})
const selectedResume = computed(
  () => parsedResumes.value.find((item) => item.id === selectedResumeId.value) || null,
)
const selectedJob = computed(
  () => jobs.value.find((item) => item.code === selectedJobCode.value) || null,
)

function unwrap(resp) {
  if (Array.isArray(resp)) return resp
  if (resp && Array.isArray(resp.items)) return resp.items
  return []
}

function formatDate(value) {
  if (!value) return '暂无时间'
  return new Date(value).toLocaleString()
}

function scoreOf(item) {
  const score = item.score_report?.overall_score ?? item.overall_score
  return score == null ? null : Math.round(score)
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
    if (!selectedResumeId.value && parsedResumes.value.length) {
      selectedResumeId.value = parsedResumes.value[0].id
    }
    if (!selectedJobCode.value && jobs.value.length) {
      selectedJobCode.value = jobs.value[0].code
    }
  } catch (err) {
    error.value = err?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function startInterview() {
  if (!selectedResumeId.value) {
    ElMessage.warning('请先选择一份已解析简历')
    return
  }
  if (!selectedJobCode.value) {
    ElMessage.warning('请先选择目标岗位')
    return
  }
  router.push({
    path: '/interviews',
    query: {
      resume_id: selectedResumeId.value,
      job_code: selectedJobCode.value,
    },
  })
}

function openInterview(item) {
  if (item.status === 'completed') {
    router.push(`/reports/${item.id}`)
    return
  }
  router.push(`/interviews/${item.id}`)
}

onMounted(load)
</script>

<template>
  <div class="dashboard user-home">
    <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />

    <section class="home-hero">
      <div class="hero-copy">
        <p class="section-kicker">AI MOCK INTERVIEW</p>
        <h1>面试记录</h1>
        <p>
          选择一份已解析简历，匹配目标岗位，直接进入多轮 AI 模拟面试。
          历史面试、评分报告和继续作答都在这里。
        </p>
        <div class="hero-stats">
          <span><strong>{{ interviews.length }}</strong> 场面试</span>
          <span><strong>{{ completedCount }}</strong> 份报告</span>
          <span><strong>{{ activeCount }}</strong> 个进行中</span>
          <span><strong>{{ latestScore ?? '-' }}</strong> 最新评分</span>
        </div>
      </div>

      <div class="resume-start-panel">
        <div class="panel-head">
          <Sparkles :size="18" />
          <strong>开始新面试</strong>
        </div>
        <el-form label-position="top">
          <el-form-item label="选择简历">
            <el-select
              v-model="selectedResumeId"
              placeholder="选择已解析简历"
              style="width: 100%"
              :disabled="!parsedResumes.length"
            >
              <el-option
                v-for="resume in parsedResumes"
                :key="resume.id"
                :value="resume.id"
                :label="`#${resume.id} ${resume.filename}`"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="目标岗位">
            <el-select
              v-model="selectedJobCode"
              placeholder="选择岗位"
              style="width: 100%"
              :disabled="!jobs.length"
            >
              <el-option
                v-for="job in jobs"
                :key="job.code"
                :value="job.code"
                :label="job.title"
              />
            </el-select>
          </el-form-item>
        </el-form>
        <div v-if="selectedResume" class="resume-note">
          <FileText :size="14" />
          <span>{{ selectedResume.target_position || '未填写目标岗位' }}</span>
        </div>
        <div v-if="selectedJob" class="resume-note">
          <Briefcase :size="14" />
          <span>{{ selectedJob.description || selectedJob.title }}</span>
        </div>
        <el-button
          type="primary"
          size="large"
          :icon="Play"
          :disabled="!selectedResumeId || !selectedJobCode"
          @click="startInterview"
        >
          开启 AI 模拟面试
        </el-button>
        <el-button
          v-if="!parsedResumes.length"
          class="upload-empty"
          :icon="Upload"
          @click="router.push('/resumes')"
        >
          先上传简历
        </el-button>
      </div>
    </section>

    <section class="quick-lanes" aria-label="快捷入口">
      <button type="button" class="lane lane-upload" @click="router.push('/resumes')">
        <Upload :size="20" />
        <span>
          <strong>上传简历</strong>
          <small>PDF 持久化解析</small>
        </span>
        <ArrowRight :size="16" />
      </button>
      <button type="button" class="lane lane-job" @click="router.push('/jobs')">
        <Briefcase :size="20" />
        <span>
          <strong>岗位匹配</strong>
          <small>让 Agent 推荐方向</small>
        </span>
        <ArrowRight :size="16" />
      </button>
      <button type="button" class="lane lane-report" @click="router.push('/reports')">
        <FileText :size="20" />
        <span>
          <strong>评分报告</strong>
          <small>查看能力雷达</small>
        </span>
        <ArrowRight :size="16" />
      </button>
    </section>

    <section class="interview-records">
      <div class="records-head">
        <div>
          <p class="section-kicker">RECORDS</p>
          <h2>我的面试记录</h2>
        </div>
        <el-button text :icon="RefreshCw" :loading="loading" @click="load">刷新</el-button>
      </div>

      <div v-loading="loading" class="records-body">
        <div v-if="!latestInterviews.length" class="empty-records">
          <div class="empty-icon">🎯</div>
          <strong>还没有面试记录</strong>
          <p>上传简历并选择岗位后，开始你的第一次 AI 模拟面试。</p>
          <el-button type="primary" @click="router.push('/resumes')">上传简历</el-button>
        </div>

        <article
          v-for="item in latestInterviews"
          v-else
          :key="item.id"
          class="record-card"
          @click="openInterview(item)"
        >
          <div class="record-main">
            <div class="record-title">
              <strong>{{ item.job_title || item.job_code || '模拟面试' }}</strong>
              <el-tag :type="statusMeta[item.status]?.type || 'info'" size="small">
                {{ statusMeta[item.status]?.label || item.status }}
              </el-tag>
            </div>
            <p>
              <Clock3 :size="14" />
              {{ formatDate(item.created_at) }}
            </p>
          </div>
          <div class="record-side">
            <span v-if="scoreOf(item) != null" class="score-pill">
              {{ scoreOf(item) }} 分
            </span>
            <span v-else class="score-pill pending">待评分</span>
            <el-button type="primary" plain>
              {{ item.status === 'completed' ? '查看报告' : '继续面试' }}
            </el-button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.user-home {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.home-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 22px;
  align-items: stretch;
}

.hero-copy,
.resume-start-panel,
.interview-records {
  border: 1px solid #dde6f1;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 18px 44px rgba(28, 43, 68, 0.08);
}

.hero-copy {
  min-height: 256px;
  padding: 34px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(240, 247, 255, 0.9)),
    radial-gradient(circle at 88% 18%, rgba(255, 79, 129, 0.18), transparent 16rem);
}

.section-kicker {
  margin: 0 0 8px;
  color: #6b7b91;
  font-size: 12px;
  font-weight: 800;
}

.hero-copy h1,
.records-head h2 {
  margin: 0;
  color: #172033;
}

.hero-copy h1 {
  font-size: 40px;
  line-height: 1.15;
}

.hero-copy p:not(.section-kicker) {
  max-width: 660px;
  margin: 14px 0 0;
  color: #5f6f89;
  font-size: 15px;
  line-height: 1.8;
}

.hero-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 24px;
}

.hero-stats span {
  min-width: 118px;
  padding: 10px 12px;
  border: 1px solid #dfe8f4;
  border-radius: 8px;
  color: #5f6f89;
  background: #fff;
  font-size: 13px;
}

.hero-stats strong {
  color: #172033;
  font-size: 20px;
}

.resume-start-panel {
  padding: 22px;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 18px;
  color: #172033;
}

.resume-note {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-bottom: 10px;
  color: #6b7b91;
  font-size: 12px;
  line-height: 1.6;
}

.resume-start-panel .el-button {
  width: 100%;
  margin-top: 10px;
  border-radius: 8px;
}

.upload-empty {
  margin-left: 0;
}

.quick-lanes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.lane {
  min-height: 82px;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 1px solid #dde6f1;
  border-radius: 8px;
  color: #172033;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease;
}

.lane:hover {
  transform: translateY(-2px);
  border-color: #b8cdf0;
  box-shadow: 0 14px 30px rgba(28, 43, 68, 0.1);
}

.lane svg:first-child {
  width: 38px;
  height: 38px;
  padding: 9px;
  border-radius: 8px;
}

.lane-upload svg:first-child {
  color: #0f766e;
  background: #dff8f4;
}

.lane-job svg:first-child {
  color: #b45309;
  background: #fff1d6;
}

.lane-report svg:first-child {
  color: #be185d;
  background: #ffe4ef;
}

.lane strong,
.lane small {
  display: block;
}

.lane small {
  margin-top: 4px;
  color: #7b889a;
}

.interview-records {
  padding: 24px;
}

.records-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.records-head h2 {
  font-size: 24px;
}

.records-body {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty-records {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px dashed #ccd8e8;
  border-radius: 8px;
  color: #5f6f89;
  background: #f8fbff;
  text-align: center;
}

.empty-icon {
  font-size: 38px;
}

.empty-records strong {
  color: #172033;
  font-size: 16px;
}

.empty-records p {
  margin: 0;
  font-size: 13px;
}

.record-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px;
  align-items: center;
  padding: 16px;
  border: 1px solid #e3eaf3;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition:
    transform 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}

.record-card:hover {
  transform: translateY(-1px);
  border-color: #b8cdf0;
  box-shadow: 0 12px 26px rgba(28, 43, 68, 0.08);
}

.record-title,
.record-side {
  display: flex;
  align-items: center;
  gap: 10px;
}

.record-title strong {
  color: #172033;
  font-size: 16px;
}

.record-main p {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 8px 0 0;
  color: #7b889a;
  font-size: 13px;
}

.score-pill {
  min-width: 66px;
  padding: 7px 10px;
  border-radius: 999px;
  color: #0f766e;
  background: #dff8f4;
  font-size: 13px;
  font-weight: 800;
  text-align: center;
}

.score-pill.pending {
  color: #7b889a;
  background: #eef2f6;
}

@media (max-width: 980px) {
  .home-hero,
  .quick-lanes {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .hero-copy,
  .resume-start-panel,
  .interview-records {
    padding: 18px;
  }

  .hero-copy h1 {
    font-size: 32px;
  }

  .record-card {
    grid-template-columns: 1fr;
  }

  .record-side {
    justify-content: space-between;
  }
}
</style>
