<script setup>
/**
 * 模拟面试主控台：
 *  - 左：会话列表 + 新建表单（resume + job + 题量 + 幂等 key 防抖）；
 *  - 右：串行 Q&A——一次只展示一道题，进度条 + 计时器 + 字数；
 *  - 草稿：每题作答自动写入 localStorage（key=interview:{id}:answer:{qid}）；
 *  - 路由 query 支持 resume_id / job_code 预填（来自 JobRecommend 跳转）。
 */
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Flag,
  MessageSquarePlus,
  Pencil,
  Save,
  Trash2,
} from 'lucide-vue-next'
import { interviewApi, jobApi, resumeApi } from '@/api/modules'

const route = useRoute()
const router = useRouter()

const resumes = ref([])
const jobs = ref([])
const interviews = ref([])
const current = ref(null)
const currentIndex = ref(0)
const draftAnswer = ref('')
const elapsed = ref(0)
const submitting = ref(false)
const finishing = ref(false)
const creating = ref(false)
const loading = ref(false)
const sidebarLoading = ref(false)
const aiFeedback = reactive({
  loading: false,
  content: '',
  error: '',
  event: '',
})

const form = reactive({
  resume_id: route.query.resume_id ? Number(route.query.resume_id) : '',
  job_code: route.query.job_code || '',
  question_count: 6,
})

const statusMeta = {
  created: { type: 'info', label: '已创建' },
  generating: { type: 'warning', label: '生成中' },
  in_progress: { type: 'primary', label: '进行中' },
  scoring: { type: 'warning', label: '评分中' },
  completed: { type: 'success', label: '已完成' },
  failed: { type: 'danger', label: '失败' },
  cancelled: { type: 'info', label: '已取消' },
}

const sortedQuestions = computed(() =>
  current.value
    ? [...current.value.questions].sort((a, b) => a.position - b.position)
    : [],
)
const currentQuestion = computed(() => sortedQuestions.value[currentIndex.value] || null)
const answeredMap = computed(() => {
  const map = new Map()
  ;(current.value?.answers || []).forEach((a) => map.set(a.question_id, a))
  return map
})
const answeredCount = computed(
  () => sortedQuestions.value.filter((q) => answeredMap.value.has(q.id)).length,
)
const progress = computed(() =>
  sortedQuestions.value.length
    ? Math.round((answeredCount.value / sortedQuestions.value.length) * 100)
    : 0,
)
const charCount = computed(() => draftAnswer.value.length)
const canFinish = computed(
  () =>
    !!current.value &&
    ['in_progress', 'created'].includes(current.value.status) &&
    answeredCount.value === sortedQuestions.value.length &&
    sortedQuestions.value.length > 0,
)

let timer = null
let questionStartedAt = Date.now()
let streamController = null

function formatElapsed(s) {
  const m = String(Math.floor(s / 60)).padStart(2, '0')
  const sec = String(s % 60).padStart(2, '0')
  return `${m}:${sec}`
}

function startTimer() {
  stopTimer()
  questionStartedAt = Date.now()
  elapsed.value = 0
  timer = window.setInterval(() => {
    elapsed.value = Math.floor((Date.now() - questionStartedAt) / 1000)
  }, 1000)
}
function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

function draftKey(interviewId, questionId) {
  return `aimi:interview:${interviewId}:q:${questionId}`
}
function loadDraft() {
  if (!current.value || !currentQuestion.value) return
  const cached = localStorage.getItem(draftKey(current.value.id, currentQuestion.value.id))
  const submitted = answeredMap.value.get(currentQuestion.value.id)
  draftAnswer.value = cached ?? submitted?.answer ?? ''
}
function saveDraft() {
  if (!current.value || !currentQuestion.value) return
  if (draftAnswer.value) {
    localStorage.setItem(
      draftKey(current.value.id, currentQuestion.value.id),
      draftAnswer.value,
    )
  } else {
    localStorage.removeItem(draftKey(current.value.id, currentQuestion.value.id))
  }
}
watch(draftAnswer, () => saveDraft())

function unwrap(resp) {
  if (Array.isArray(resp)) return resp
  if (resp && Array.isArray(resp.items)) return resp.items
  return []
}

async function loadSidebar() {
  sidebarLoading.value = true
  try {
    const [resumeData, jobData, interviewData] = await Promise.all([
      resumeApi.list({ page: 1, page_size: 50 }),
      jobApi.list(),
      interviewApi.list({ page: 1, page_size: 30 }),
    ])
    resumes.value = unwrap(resumeData).filter((r) => r.parse_status === 'parsed')
    jobs.value = unwrap(jobData)
    interviews.value = unwrap(interviewData)
    if (!form.resume_id && resumes.value.length) form.resume_id = resumes.value[0].id
    if (!form.job_code && jobs.value.length) form.job_code = jobs.value[0].code
  } catch (err) {
    ElMessage.error(err?.message || '加载失败')
  } finally {
    sidebarLoading.value = false
  }
}

async function pickInterview(item) {
  loading.value = true
  try {
    current.value = await interviewApi.get(item.id)
    currentIndex.value = 0
    resetAiFeedback()
    await nextTick()
    startTimer()
    loadDraft()
  } catch (err) {
    ElMessage.error(err?.message || '加载面试失败')
  } finally {
    loading.value = false
  }
}

async function refreshCurrent() {
  if (!current.value) return
  try {
    current.value = await interviewApi.get(current.value.id)
  } catch (err) {
    ElMessage.error(err?.message || '刷新失败')
  }
}

async function createInterview() {
  if (!form.resume_id || !form.job_code) {
    ElMessage.warning('请选择简历与岗位')
    return
  }
  creating.value = true
  try {
    const idempotencyKey =
      `${form.resume_id}-${form.job_code}-${form.question_count}-${Date.now()}`
    const created = await interviewApi.create({
      resume_id: Number(form.resume_id),
      job_code: form.job_code,
      question_count: Number(form.question_count),
      idempotency_key: idempotencyKey,
    })
    ElMessage.success('面试已创建')
    interviews.value = [created, ...interviews.value]
    current.value = created
    currentIndex.value = 0
    resetAiFeedback()
    await nextTick()
    startTimer()
    loadDraft()
  } catch (err) {
    ElMessage.error(err?.message || '创建失败')
  } finally {
    creating.value = false
  }
}

function resetAiFeedback() {
  aiFeedback.loading = false
  aiFeedback.content = ''
  aiFeedback.error = ''
  aiFeedback.event = ''
}

async function runFollowupStream(questionId) {
  if (!current.value || !questionId) return
  if (streamController) streamController.abort()
  streamController = new AbortController()
  aiFeedback.loading = true
  aiFeedback.content = ''
  aiFeedback.error = ''
  aiFeedback.event = 'followup_started'
  try {
    await interviewApi.stream(current.value.id, {
      params: { mode: 'followup', question_id: questionId },
      signal: streamController.signal,
      onEvent: ({ event, data }) => {
        aiFeedback.event = event
        if (event === 'followup_delta') aiFeedback.content += data.content || ''
        if (event === 'followup_done') aiFeedback.content = data.content || aiFeedback.content
        if (event === 'error') aiFeedback.error = data.message || 'AI 追问生成失败'
      },
    })
  } catch (err) {
    if (err.name !== 'AbortError') aiFeedback.error = err?.message || 'AI 追问生成失败'
  } finally {
    aiFeedback.loading = false
    streamController = null
  }
}

async function submitAnswer() {
  if (!currentQuestion.value) return
  const text = draftAnswer.value.trim()
  if (text.length < 5) {
    ElMessage.warning('回答至少 5 个字')
    return
  }
  submitting.value = true
  try {
    const duration = Date.now() - questionStartedAt
    const updated = await interviewApi.answer(current.value.id, {
      question_id: currentQuestion.value.id,
      answer: text,
      duration_ms: duration,
    })
    const answeredQuestionId = currentQuestion.value.id
    current.value = updated
    localStorage.removeItem(draftKey(current.value.id, answeredQuestionId))
    ElMessage.success('已提交')
    await runFollowupStream(answeredQuestionId)
  } catch (err) {
    ElMessage.error(err?.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

function go(delta) {
  const next = currentIndex.value + delta
  if (next < 0 || next >= sortedQuestions.value.length) return
  currentIndex.value = next
  resetAiFeedback()
  startTimer()
  loadDraft()
}

async function finish() {
  await ElMessageBox.confirm('确认结束面试并出具评分报告？', '完成面试', {
    confirmButtonText: '完成',
    cancelButtonText: '继续答题',
    type: 'warning',
  })
  finishing.value = true
  try {
    current.value = await interviewApi.finish(current.value.id)
    ElMessage.success('面试已完成，正在生成报告')
    router.push(`/reports/${current.value.id}`)
  } catch (err) {
    ElMessage.error(err?.message || '完成失败')
  } finally {
    finishing.value = false
  }
}

async function cancelInterview() {
  await ElMessageBox.confirm('确认取消该面试？已提交的回答将保留但不会出报告。', '取消面试', {
    confirmButtonText: '取消面试',
    cancelButtonText: '继续',
    type: 'warning',
  })
  try {
    current.value = await interviewApi.cancel(current.value.id)
    ElMessage.success('已取消')
    await loadSidebar()
  } catch (err) {
    ElMessage.error(err?.message || '取消失败')
  }
}

async function removeInterview(item) {
  await ElMessageBox.confirm(`删除 #${item.id} ${item.job_title}？此操作不可恢复。`, '删除面试', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  try {
    await interviewApi.delete(item.id)
    if (current.value?.id === item.id) current.value = null
    interviews.value = interviews.value.filter((i) => i.id !== item.id)
    ElMessage.success('已删除')
  } catch (err) {
    ElMessage.error(err?.message || '删除失败')
  }
}

watch(
  () => route.params.id,
  async (id) => {
    if (id) {
      try {
        current.value = await interviewApi.get(Number(id))
        currentIndex.value = 0
        resetAiFeedback()
        startTimer()
        loadDraft()
      } catch (err) {
        ElMessage.error(err?.message || '面试不存在')
      }
    }
  },
  { immediate: false },
)

onMounted(async () => {
  await loadSidebar()
  if (route.params.id) {
    try {
      current.value = await interviewApi.get(Number(route.params.id))
      startTimer()
      loadDraft()
    } catch (err) {
      ElMessage.error('面试不存在或已被删除')
    }
  }
})

onUnmounted(() => {
  stopTimer()
  if (streamController) streamController.abort()
})
</script>

<template>
  <div class="mock-page">
    <div class="layout">
      <!-- 左侧：新建 + 历史 -->
      <aside class="aside">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <h3><MessageSquarePlus :size="16" /> 新建面试</h3>
            </div>
          </template>
          <el-form label-position="top" size="small">
            <el-form-item label="简历">
              <el-select
                v-model="form.resume_id"
                placeholder="选择已解析简历"
                style="width: 100%"
              >
                <el-option
                  v-for="r in resumes"
                  :key="r.id"
                  :value="r.id"
                  :label="`#${r.id} ${r.filename}`"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="岗位">
              <el-select v-model="form.job_code" placeholder="选择岗位" style="width: 100%">
                <el-option
                  v-for="j in jobs"
                  :key="j.code"
                  :value="j.code"
                  :label="j.title"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="题量">
              <el-input-number v-model="form.question_count" :min="1" :max="12" />
            </el-form-item>
            <el-button
              type="primary"
              :loading="creating"
              :disabled="!form.resume_id || !form.job_code"
              style="width: 100%"
              @click="createInterview"
            >
              生成题目并开始
            </el-button>
            <p v-if="!resumes.length" class="muted hint">
              暂无已解析简历，<el-button text type="primary" @click="router.push('/resumes')">去上传</el-button>
            </p>
          </el-form>
        </el-card>

        <el-card shadow="never" class="mt">
          <template #header>
            <div class="card-head">
              <h3>历史面试</h3>
              <span class="muted">{{ interviews.length }}</span>
            </div>
          </template>
          <el-skeleton v-if="sidebarLoading" :rows="3" animated />
          <el-empty v-else-if="!interviews.length" description="尚无面试记录" :image-size="60" />
          <ul v-else class="history">
            <li
              v-for="item in interviews"
              :key="item.id"
              :class="{ active: current?.id === item.id }"
              @click="pickInterview(item)"
            >
              <div class="row">
                <strong>#{{ item.id }} {{ item.job_title }}</strong>
                <el-tag :type="statusMeta[item.status]?.type" size="small">
                  {{ statusMeta[item.status]?.label || item.status }}
                </el-tag>
              </div>
              <div class="row sub">
                <small class="muted">{{ new Date(item.created_at).toLocaleDateString() }}</small>
                <el-button
                  text
                  type="danger"
                  size="small"
                  :icon="Trash2"
                  @click.stop="removeInterview(item)"
                />
              </div>
            </li>
          </ul>
        </el-card>
      </aside>

      <!-- 右侧：考场 -->
      <main class="stage">
        <el-empty
          v-if="!current"
          description="选择左侧已有面试，或在上方新建一场"
          :image-size="120"
        />

        <template v-else>
          <header class="stage-head">
            <div>
              <p class="eyebrow">
                #{{ current.id }} · {{ current.job_title }}
                <el-tag :type="statusMeta[current.status]?.type" size="small">
                  {{ statusMeta[current.status]?.label }}
                </el-tag>
              </p>
              <h2>
                第 {{ currentIndex + 1 }} 题 / 共 {{ sortedQuestions.length }} 题
                <el-tag size="small" effect="plain" type="info">
                  <Clock :size="12" /> {{ formatElapsed(elapsed) }}
                </el-tag>
              </h2>
            </div>
            <div class="head-actions">
              <el-button
                v-if="current.status === 'in_progress' || current.status === 'created'"
                type="warning"
                plain
                @click="cancelInterview"
              >
                取消面试
              </el-button>
              <el-button
                type="success"
                :loading="finishing"
                :disabled="!canFinish"
                @click="finish"
              >
                <Flag :size="14" /><span style="margin-left: 4px">完成并出报告</span>
              </el-button>
            </div>
          </header>

          <el-progress
            :percentage="progress"
            :format="() => `${answeredCount} / ${sortedQuestions.length}`"
          />

          <el-card v-if="currentQuestion" shadow="never" class="qa">
            <div class="q-meta">
              <el-tag size="small" type="primary">{{ currentQuestion.type }}</el-tag>
              <el-tag size="small" type="warning">{{ currentQuestion.difficulty }}</el-tag>
              <el-tag size="small">{{ currentQuestion.skill }}</el-tag>
              <span class="muted">题号 #{{ currentQuestion.position }}</span>
            </div>
            <h3 class="q-text">{{ currentQuestion.question }}</h3>

            <el-collapse v-if="currentQuestion.rubric?.length">
              <el-collapse-item title="评分要点（参考，提交后给评委用）">
                <ul class="rubric">
                  <li v-for="r in currentQuestion.rubric" :key="r">{{ r }}</li>
                </ul>
              </el-collapse-item>
            </el-collapse>

            <div class="answer-block">
              <div class="answer-head">
                <span><Pencil :size="14" /> 你的回答</span>
                <span class="muted">{{ charCount }} / 8000</span>
              </div>
              <el-input
                v-model="draftAnswer"
                type="textarea"
                :rows="10"
                placeholder="尽量结构化作答：背景 / 思路 / 实现 / 结果"
                maxlength="8000"
                :disabled="['completed', 'cancelled', 'failed'].includes(current.status)"
              />
              <p class="muted hint">
                <Save :size="12" /> 草稿已自动保存到本地，刷新或关闭页面后再回来仍在。
              </p>
            </div>

            <div v-if="answeredMap.has(currentQuestion.id)" class="answered-banner">
              <CheckCircle2 :size="14" />
              已提交（可重新作答覆盖）·
              <span v-if="answeredMap.get(currentQuestion.id)?.score != null">
                得分 {{ answeredMap.get(currentQuestion.id).score }} · {{ answeredMap.get(currentQuestion.id).comment }}
              </span>
            </div>

            <div
              v-if="aiFeedback.loading || aiFeedback.content || aiFeedback.error"
              class="ai-feedback"
            >
              <div class="ai-feedback-head">
                <span>AI 面试官反馈</span>
                <el-tag v-if="aiFeedback.loading" size="small" type="warning">生成中</el-tag>
                <el-tag v-else size="small" type="success">已生成</el-tag>
              </div>
              <p v-if="aiFeedback.content">{{ aiFeedback.content }}</p>
              <p v-if="aiFeedback.error" class="ai-feedback-error">{{ aiFeedback.error }}</p>
            </div>

            <div class="qa-actions">
              <el-button :icon="ChevronLeft" :disabled="currentIndex === 0" @click="go(-1)">
                上一题
              </el-button>
              <el-button
                type="primary"
                :loading="submitting"
                :disabled="['completed', 'cancelled', 'failed'].includes(current.status)"
                @click="submitAnswer"
              >
                提交本题
              </el-button>
              <el-button
                :disabled="currentIndex === sortedQuestions.length - 1"
                @click="go(1)"
              >
                下一题 <ChevronRight :size="14" />
              </el-button>
            </div>
          </el-card>

          <el-card v-if="current.status === 'failed'" shadow="never" class="error-card">
            <strong>面试生成失败</strong>
            <p class="muted">{{ current.status_reason || '未知原因，请新建一场重试' }}</p>
          </el-card>
        </template>
      </main>
    </div>
  </div>
</template>

<style scoped>
.mock-page { display: flex; flex-direction: column; }
.layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; align-items: flex-start; }
.aside { display: flex; flex-direction: column; gap: 12px; position: sticky; top: 12px; }
.mt { margin-top: 0; }
.stage { display: flex; flex-direction: column; gap: 14px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-head h3 { margin: 0; font-size: 14px; color: #0f172a; display: flex; align-items: center; gap: 6px; }
.muted { color: #94a3b8; font-size: 12px; }
.hint { display: inline-flex; align-items: center; gap: 4px; margin-top: 4px; }
.history { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.history li {
  border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; cursor: pointer;
  background: #fff; transition: border-color .15s;
}
.history li:hover { border-color: #93c5fd; }
.history li.active { border-color: #3b82f6; background: #eff6ff; }
.history .row { display: flex; justify-content: space-between; align-items: center; }
.history .sub { margin-top: 4px; }
.history strong { font-size: 13px; color: #0f172a; }
.stage-head {
  display: flex; justify-content: space-between; align-items: flex-end;
  background: #fff; padding: 18px 22px; border-radius: 14px;
  box-shadow: 0 4px 18px -10px rgba(15,23,42,.15);
}
.stage-head .eyebrow { margin: 0 0 4px; color: #94a3b8; font-size: 11px; letter-spacing: 1.5px; display: flex; gap: 8px; align-items: center; }
.stage-head h2 { margin: 0; color: #0f172a; font-size: 20px; display: flex; align-items: center; gap: 12px; }
.head-actions { display: flex; gap: 10px; }
.qa { border: 1px solid #e2e8f0; }
.q-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.q-text { margin: 6px 0 14px; color: #0f172a; line-height: 1.6; font-size: 18px; }
.rubric { margin: 0; padding-left: 20px; color: #475569; }
.rubric li { line-height: 1.7; font-size: 13px; }
.answer-block { margin-top: 14px; }
.answer-head {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px; color: #475569; margin-bottom: 6px;
}
.answered-banner {
  margin-top: 10px; padding: 8px 12px; border-radius: 8px;
  background: #ecfdf5; color: #065f46; font-size: 12px;
  display: flex; align-items: center; gap: 6px;
}
.ai-feedback {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
}
.ai-feedback-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #1e3a8a;
  font-size: 13px;
  font-weight: 600;
}
.ai-feedback p {
  margin: 8px 0 0;
  color: #1f2937;
  line-height: 1.7;
  font-size: 13px;
  white-space: pre-wrap;
}
.ai-feedback-error {
  color: #b91c1c;
}
.qa-actions { display: flex; justify-content: space-between; gap: 8px; margin-top: 14px; }
.error-card { background: #fef2f2; border: 1px solid #fecaca; }
.error-card strong { color: #b91c1c; }
@media (max-width: 1024px) {
  .layout { grid-template-columns: 1fr; }
  .aside { position: static; }
}
</style>
