<script setup>
/**
 * 模拟面试主控台：
 *  - 左：会话列表 + 新建表单（resume + job + 轮次 + 幂等 key 防抖）；
 *  - 右：AI 面试官与候选人的连续消息流，发送后自动进入下一轮；
 *  - 草稿：当前轮回复自动写入 localStorage（key=interview:{id}:answer:{qid}）；
 *  - 路由 query 支持 resume_id / job_code 预填（来自 JobRecommend 跳转）。
 */
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  CheckCircle2,
  Circle,
  Clock,
  Flag,
  MessageSquarePlus,
  Pencil,
  Save,
  SendHorizontal,
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
const chatRoomRef = ref(null)
const autosaveState = ref('saved')
const feedbackByQuestion = reactive({})
const aiFeedback = reactive({
  loading: false,
  content: '',
  error: '',
  event: '',
})
const scoringFeedback = reactive({
  loading: false,
  event: '',
  error: '',
  overallScore: null,
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
const isReadonly = computed(() =>
  ['completed', 'cancelled', 'failed'].includes(current.value?.status),
)
const awaitingInterviewer = computed(() => aiFeedback.loading)
const isCurrentAnswered = computed(() =>
  !!currentQuestion.value && answeredMap.value.has(currentQuestion.value.id),
)
const composerDisabled = computed(() =>
  isReadonly.value ||
  submitting.value ||
  awaitingInterviewer.value ||
  !currentQuestion.value ||
  isCurrentAnswered.value,
)
const composerDisabledReason = computed(() => {
  if (isReadonly.value) return '当前面试已结束，不能继续提交'
  if (submitting.value) return '正在提交回答'
  if (awaitingInterviewer.value) return 'AI 面试官正在思考，请稍等'
  if (!currentQuestion.value) return '暂无当前问题'
  if (isCurrentAnswered.value) return '当前问题已回答，等待下一题'
  if (draftAnswer.value.trim().length < 5) return '回答至少 5 个字后可以发送'
  return '可以发送'
})
const canFinish = computed(
  () =>
    !!current.value &&
    ['in_progress', 'created'].includes(current.value.status) &&
    answeredCount.value === sortedQuestions.value.length &&
    sortedQuestions.value.length > 0,
)
const currentTurnText = computed(() => {
  if (!current.value) return ''
  if (isReadonly.value) return statusMeta[current.value.status]?.label || '面试已结束'
  if (canFinish.value) return '对话已完成，可以生成评分报告'
  if (awaitingInterviewer.value) return 'AI 面试官正在思考'
  return `正在进行第 ${currentIndex.value + 1} 轮对话`
})
const conversationTurns = computed(() => {
  const turns = []
  sortedQuestions.value.forEach((question, index) => {
    const answer = answeredMap.value.get(question.id)
    const feedback = feedbackByQuestion[question.id]
    const shouldReveal = index <= currentIndex.value || !!answer || !!feedback
    if (!shouldReveal) return

    turns.push({
      id: `question-${question.id}`,
      role: 'interviewer',
      type: 'question',
      question,
      eyebrow: `AI 面试官 · 第 ${question.position} 轮`,
    })

    if (answer) {
      turns.push({
        id: `answer-${question.id}`,
        role: 'candidate',
        type: 'answer',
        question,
        answer,
        eyebrow: '我的回应',
      })
    }

    if (feedback?.loading || feedback?.content || feedback?.error) {
      turns.push({
        id: `feedback-${question.id}`,
        role: 'interviewer',
        type: 'feedback',
        question,
        feedback,
        eyebrow: 'AI 面试官',
      })
    }
  })
  return turns
})
const responseQualityHints = computed(() => [
  {
    key: 'specific',
    label: '说清场景',
    done: draftAnswer.value.trim().length >= 20,
  },
  {
    key: 'evidence',
    label: '给出证据',
    done: /(\d|%|用户|性能|时间|成本|结果|指标)/.test(draftAnswer.value),
  },
  {
    key: 'tradeoff',
    label: '说明取舍',
    done: /(因为|所以|但是|取舍|权衡|风险|方案)/.test(draftAnswer.value),
  },
])
const qualityChecklist = computed(() => responseQualityHints.value)
const scoringStepIndex = computed(() => {
  const order = {
    scoring_started: 1,
    scoring_done: 2,
    report_ready: 3,
    done: 3,
  }
  return order[scoringFeedback.event] || 0
})
const scoringStatusText = computed(() => {
  if (scoringFeedback.error) return '生成失败'
  if (scoringFeedback.event === 'report_ready' || scoringFeedback.event === 'done') return '报告已就绪'
  if (scoringFeedback.event === 'scoring_done') return '评分完成'
  if (scoringFeedback.loading) return '生成中'
  return '等待生成'
})

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
  autosaveState.value = 'saving'
  if (draftAnswer.value) {
    localStorage.setItem(
      draftKey(current.value.id, currentQuestion.value.id),
      draftAnswer.value,
    )
  } else {
    localStorage.removeItem(draftKey(current.value.id, currentQuestion.value.id))
  }
  window.setTimeout(() => {
    autosaveState.value = 'saved'
  }, 160)
}
watch(draftAnswer, () => saveDraft())

function scrollConversationToBottom() {
  nextTick(() => {
    const el = chatRoomRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function syncCurrentIndexFromAnswers() {
  const nextUnanswered = sortedQuestions.value.findIndex((q) => !answeredMap.value.has(q.id))
  currentIndex.value = nextUnanswered === -1 ? Math.max(sortedQuestions.value.length - 1, 0) : nextUnanswered
}

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
    syncCurrentIndexFromAnswers()
    resetConversationFeedback()
    resetScoringFeedback()
    await nextTick()
    startTimer()
    loadDraft()
  } catch (err) {
    ElMessage.error(err?.message || '加载面试失败')
  } finally {
    loading.value = false
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
    resetConversationFeedback()
    resetScoringFeedback()
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
  if (streamController) {
    streamController.abort()
    streamController = null
  }
  aiFeedback.loading = false
  aiFeedback.content = ''
  aiFeedback.error = ''
  aiFeedback.event = ''
}

function resetConversationFeedback() {
  Object.keys(feedbackByQuestion).forEach((key) => delete feedbackByQuestion[key])
  resetAiFeedback()
}

function resetScoringFeedback() {
  if (streamController) {
    streamController.abort()
    streamController = null
  }
  scoringFeedback.loading = false
  scoringFeedback.event = ''
  scoringFeedback.error = ''
  scoringFeedback.overallScore = null
}

async function runFollowupStream(questionId) {
  if (!current.value || !questionId) return
  if (streamController) streamController.abort()
  const controller = new AbortController()
  streamController = controller
  aiFeedback.loading = true
  aiFeedback.content = ''
  aiFeedback.error = ''
  aiFeedback.event = 'followup_started'
  feedbackByQuestion[questionId] = {
    loading: true,
    content: '',
    error: '',
  }
  scrollConversationToBottom()
  try {
    await interviewApi.stream(current.value.id, {
      params: { mode: 'followup', question_id: questionId },
      signal: controller.signal,
      onEvent: ({ event, data }) => {
        aiFeedback.event = event
        if (event === 'followup_delta') {
          aiFeedback.content += data.content || ''
          feedbackByQuestion[questionId].content += data.content || ''
          scrollConversationToBottom()
        }
        if (event === 'followup_done') {
          aiFeedback.content = data.content || aiFeedback.content
          feedbackByQuestion[questionId].content = data.content || feedbackByQuestion[questionId].content
        }
        if (event === 'error') {
          aiFeedback.error = data.message || 'AI 追问生成失败'
          feedbackByQuestion[questionId].error = aiFeedback.error
        }
      },
    })
  } catch (err) {
    if (err?.name !== 'AbortError') {
      aiFeedback.error = err?.message || 'AI 追问生成失败'
      feedbackByQuestion[questionId].error = aiFeedback.error
    }
  } finally {
    if (feedbackByQuestion[questionId]) feedbackByQuestion[questionId].loading = false
    if (streamController === controller) {
      aiFeedback.loading = false
      streamController = null
    }
  }
}

async function runScoringStream() {
  if (!current.value) return
  if (streamController) streamController.abort()
  const controller = new AbortController()
  const interviewId = current.value.id
  let reportReady = false

  streamController = controller
  scoringFeedback.loading = true
  scoringFeedback.event = 'scoring_started'
  scoringFeedback.error = ''
  scoringFeedback.overallScore = null

  try {
    await interviewApi.stream(interviewId, {
      params: { mode: 'scoring' },
      signal: controller.signal,
      onEvent: ({ event, data }) => {
        scoringFeedback.event = event
        if (event === 'scoring_done') scoringFeedback.overallScore = data.overall_score ?? null
        if (event === 'report_ready') {
          reportReady = true
          scoringFeedback.overallScore = data.report?.overall_score ?? scoringFeedback.overallScore
          current.value = {
            ...current.value,
            status: 'completed',
            overall_score: scoringFeedback.overallScore,
            score_report: data.report,
          }
        }
        if (event === 'error') scoringFeedback.error = data.message || '评分报告生成失败'
      },
    })

    if (reportReady && !scoringFeedback.error) {
      ElMessage.success('评分报告已生成')
      router.push(`/reports/${interviewId}`)
    }
  } catch (err) {
    if (err?.name !== 'AbortError') scoringFeedback.error = err?.message || '评分报告生成失败'
  } finally {
    if (streamController === controller) {
      scoringFeedback.loading = false
      streamController = null
    }
  }
}

function advanceToNextQuestion(answeredQuestionId) {
  const answeredIndex = sortedQuestions.value.findIndex((q) => q.id === answeredQuestionId)
  const nextIndex = sortedQuestions.value.findIndex(
    (q, index) => index > answeredIndex && !answeredMap.value.has(q.id),
  )
  if (nextIndex === -1) {
    currentIndex.value = Math.max(answeredIndex, 0)
    draftAnswer.value = ''
    stopTimer()
    scrollConversationToBottom()
    return
  }
  currentIndex.value = nextIndex
  startTimer()
  loadDraft()
  scrollConversationToBottom()
}

async function sendAnswer() {
  if (composerDisabled.value) return
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
    draftAnswer.value = ''
    await runFollowupStream(answeredQuestionId)
    advanceToNextQuestion(answeredQuestionId)
  } catch (err) {
    ElMessage.error(err?.message || '发送失败')
  } finally {
    submitting.value = false
  }
}

async function finish() {
  await ElMessageBox.confirm('确认结束面试并出具评分报告？', '完成面试', {
    confirmButtonText: '完成',
    cancelButtonText: '继续答题',
    type: 'warning',
  })
  finishing.value = true
  resetAiFeedback()
  try {
    await runScoringStream()
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
        syncCurrentIndexFromAnswers()
        resetConversationFeedback()
        resetScoringFeedback()
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
      syncCurrentIndexFromAnswers()
      resetConversationFeedback()
      resetScoringFeedback()
      startTimer()
      loadDraft()
    } catch {
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
            <el-form-item label="对话轮次">
              <el-input-number v-model="form.question_count" :min="1" :max="12" />
            </el-form-item>
            <el-button
              type="primary"
              :loading="creating"
              :disabled="!form.resume_id || !form.job_code"
              style="width: 100%"
              @click="createInterview"
            >
              开始 AI 面试
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

      <!-- 右侧：AI 面试官对话 -->
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
                AI 对话式面试
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
                :loading="finishing || scoringFeedback.loading"
                :disabled="!canFinish || scoringFeedback.loading"
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

          <div
            v-if="scoringFeedback.loading || scoringFeedback.event || scoringFeedback.error"
            class="scoring-feedback"
          >
            <div class="scoring-feedback-head">
              <span>评分报告</span>
              <el-tag
                size="small"
                :type="scoringFeedback.error ? 'danger' : scoringFeedback.loading ? 'warning' : 'success'"
              >
                {{ scoringStatusText }}
              </el-tag>
            </div>
            <div class="scoring-steps">
              <span :class="{ active: scoringStepIndex === 1, done: scoringStepIndex > 1 }">
                开始评分
              </span>
              <span :class="{ active: scoringStepIndex === 2, done: scoringStepIndex > 2 }">
                汇总分数
              </span>
              <span :class="{ active: scoringStepIndex === 3, done: scoringStepIndex >= 3 }">
                生成报告
              </span>
            </div>
            <p v-if="scoringFeedback.overallScore != null">
              综合评分 {{ Math.round(scoringFeedback.overallScore) }}
            </p>
            <p v-if="scoringFeedback.error" class="scoring-feedback-error">
              {{ scoringFeedback.error }}
            </p>
          </div>

          <section v-if="currentQuestion" class="chat-room conversation-flow">
            <div class="conversation-status">
              <span>{{ currentTurnText }}</span>
              <el-tag v-if="currentQuestion" size="small" effect="plain">
                {{ currentQuestion.skill }}
              </el-tag>
            </div>

            <div class="interview-quality-panel">
              <div class="question-rail" aria-label="答题导航">
                <button
                  v-for="(question, index) in sortedQuestions"
                  :key="question.id"
                  type="button"
                  class="question-step"
                  :class="{
                    active: index === currentIndex,
                    answered: answeredMap.has(question.id),
                  }"
                  @click="currentIndex = index; loadDraft(); scrollConversationToBottom()"
                >
                  <CheckCircle2 v-if="answeredMap.has(question.id)" :size="13" />
                  <Circle v-else :size="13" />
                  <span>第 {{ index + 1 }} 轮</span>
                </button>
              </div>

              <div class="quality-card">
                <strong>发送前检查</strong>
                <div class="quality-list">
                  <span
                    v-for="item in qualityChecklist"
                    :key="item.key"
                    :class="{ done: item.done }"
                  >
                    {{ item.label }}
                  </span>
                </div>
              </div>
            </div>

            <div ref="chatRoomRef" class="conversation-thread">
              <article
                v-for="turn in conversationTurns"
                :key="turn.id"
                class="message-row"
                :class="turn.role === 'candidate' ? 'candidate-message' : 'interviewer-message'"
              >
                <div v-if="turn.role !== 'candidate'" class="avatar ai-avatar">AI</div>

                <div class="message-bubble" :class="{ 'feedback-bubble': turn.type === 'feedback' }">
                  <div v-if="turn.type === 'question'" class="message-kicker">
                    <span>{{ turn.eyebrow }}</span>
                    <div class="q-meta">
                      <el-tag size="small" type="primary">{{ turn.question.type }}</el-tag>
                      <el-tag size="small" type="warning">{{ turn.question.difficulty }}</el-tag>
                    </div>
                  </div>

                  <template v-if="turn.type === 'question'">
                    <p class="interviewer-copy">{{ turn.question.question }}</p>
                    <el-collapse v-if="turn.question.rubric?.length" class="rubric-collapse">
                      <el-collapse-item title="面试官观察点">
                        <ul class="rubric">
                          <li v-for="r in turn.question.rubric" :key="r">{{ r }}</li>
                        </ul>
                      </el-collapse-item>
                    </el-collapse>
                  </template>

                  <template v-else-if="turn.type === 'answer'">
                    <div class="submitted-head">
                      <span><CheckCircle2 :size="14" /> {{ turn.eyebrow }}</span>
                      <span v-if="turn.answer?.score != null">{{ turn.answer.score }} 分</span>
                    </div>
                    <p>{{ turn.answer?.answer }}</p>
                    <small v-if="turn.answer?.comment">{{ turn.answer.comment }}</small>
                  </template>

                  <template v-else>
                    <div class="ai-feedback-head">
                      <span>{{ turn.eyebrow }}追问与反馈</span>
                      <el-tag v-if="turn.feedback?.loading" size="small" type="warning">
                        AI 面试官正在思考
                      </el-tag>
                      <el-tag v-else size="small" type="success">已回应</el-tag>
                    </div>
                    <p v-if="turn.feedback?.content">{{ turn.feedback.content }}</p>
                    <p v-if="turn.feedback?.error" class="ai-feedback-error">
                      {{ turn.feedback.error }}
                    </p>
                  </template>
                </div>

                <div v-if="turn.role === 'candidate'" class="avatar user-avatar">我</div>
              </article>

              <article v-if="canFinish" class="message-row interviewer-message">
                <div class="avatar ai-avatar">AI</div>
                <div class="message-bubble final-bubble">
                  <div class="ai-feedback-head">
                    <span>AI 面试官</span>
                    <el-tag size="small" type="success">对话完成</el-tag>
                  </div>
                  <p>这轮面试已经结束。点击右上角生成综合评分报告，我会汇总你的回答表现。</p>
                </div>
              </article>
            </div>

            <section v-if="!canFinish" class="answer-composer">
              <div class="answer-head">
                <span><Pencil :size="14" /> 回复 AI 面试官</span>
                <span class="muted">{{ charCount }} / 8000 · {{ autosaveState === 'saving' ? '保存中' : '已保存' }}</span>
              </div>
              <el-input
                v-model="draftAnswer"
                type="textarea"
                :rows="5"
                placeholder="像真实面试一样直接开口回答。说完这一轮，AI 面试官会给出反馈并继续追问。"
                maxlength="8000"
                :disabled="composerDisabled"
                @keydown.ctrl.enter.prevent="sendAnswer"
                @keydown.meta.enter.prevent="sendAnswer"
              />
              <div class="composer-foot">
                <p class="muted hint">
                  <Save :size="12" /> {{ composerDisabledReason }}
                </p>
                <el-button
                  type="primary"
                  :loading="submitting || awaitingInterviewer"
                  :disabled="composerDisabled"
                  @click="sendAnswer"
                >
                  <SendHorizontal :size="15" />
                  发送给面试官
                </el-button>
              </div>
            </section>
          </section>

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
  border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; cursor: pointer;
  background: #fff; transition: border-color .15s;
}
.history li:hover { border-color: #93c5fd; }
.history li.active { border-color: #3b82f6; background: #eff6ff; }
.history .row { display: flex; justify-content: space-between; align-items: center; }
.history .sub { margin-top: 4px; }
.history strong { font-size: 13px; color: #0f172a; }
.stage-head {
  display: flex; justify-content: space-between; align-items: flex-end;
  background: #fff; padding: 18px 22px; border-radius: 8px;
  box-shadow: 0 4px 18px -10px rgba(15,23,42,.15);
}
.stage-head .eyebrow { margin: 0 0 4px; color: #94a3b8; font-size: 11px; letter-spacing: 1.5px; display: flex; gap: 8px; align-items: center; }
.stage-head h2 { margin: 0; color: #0f172a; font-size: 20px; display: flex; align-items: center; gap: 12px; }
.head-actions { display: flex; gap: 10px; }
.q-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rubric { margin: 0; padding-left: 20px; color: #475569; }
.rubric li { line-height: 1.7; font-size: 13px; }
.answer-head {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px; color: #475569; margin-bottom: 6px;
}
.ai-feedback-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #1e3a8a;
  font-size: 13px;
  font-weight: 600;
}
.feedback-bubble p,
.final-bubble p {
  margin: 8px 0 0;
  color: #1f2937;
  line-height: 1.7;
  font-size: 13px;
  white-space: pre-wrap;
}
.ai-feedback-error {
  color: #b91c1c;
}
.scoring-feedback {
  padding: 12px 14px;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  background: #fff7ed;
}
.scoring-feedback-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #9a3412;
  font-size: 13px;
  font-weight: 600;
}
.scoring-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.scoring-steps span {
  min-height: 28px;
  border: 1px solid #fed7aa;
  border-radius: 6px;
  background: #fff;
  color: #9a3412;
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.scoring-steps span.active {
  background: #ffedd5;
  border-color: #fb923c;
  font-weight: 600;
}
.scoring-steps span.done {
  background: #ecfdf5;
  border-color: #86efac;
  color: #166534;
}
.scoring-feedback p {
  margin: 8px 0 0;
  color: #7c2d12;
  line-height: 1.7;
  font-size: 13px;
}
.scoring-feedback-error {
  color: #b91c1c;
}
.error-card { background: #fef2f2; border: 1px solid #fecaca; }
.error-card strong { color: #b91c1c; }
.chat-room {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px;
  border: 1px solid #dce5f0;
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(248, 251, 255, 0.92)),
    radial-gradient(circle at 12% 10%, rgba(64, 150, 255, 0.13), transparent 20rem);
}
.conversation-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}

.interview-quality-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 240px;
  gap: 12px;
  align-items: stretch;
}

.question-rail,
.quality-card {
  border: 1px solid #dce5f0;
  border-radius: 8px;
  background: #fff;
}

.question-rail {
  min-height: 58px;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow-x: auto;
  padding: 10px;
}

.question-step {
  min-width: 84px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid #d8e3ef;
  border-radius: 8px;
  color: #64748b;
  background: #f8fbff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.question-step.active {
  color: #1d4ed8;
  border-color: #93c5fd;
  background: #eff6ff;
}

.question-step.answered {
  color: #0f766e;
  border-color: #99f6e4;
  background: #ecfdf5;
}

.quality-card {
  padding: 12px;
}

.quality-card strong {
  display: block;
  margin-bottom: 8px;
  color: #172033;
  font-size: 13px;
}

.quality-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.quality-list span {
  min-height: 26px;
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border: 1px solid #d8e3ef;
  border-radius: 999px;
  color: #64748b;
  background: #f8fbff;
  font-size: 12px;
  font-weight: 700;
}

.quality-list span.done {
  color: #0f766e;
  border-color: #99f6e4;
  background: #ecfdf5;
}

.conversation-thread {
  max-height: min(62vh, 720px);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-right: 4px;
  scroll-behavior: smooth;
}
.message-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.candidate-message {
  justify-content: flex-end;
}
.avatar {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 800;
}
.ai-avatar {
  color: #172033;
  background: #fff;
  border: 2px solid #253044;
}
.user-avatar {
  color: #fff;
  background: linear-gradient(135deg, #2f7df6, #15b8a6);
}
.message-bubble {
  max-width: min(760px, calc(100% - 54px));
  padding: 16px 18px;
  border: 1px solid #dfe7f1;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 12px 30px rgba(28, 43, 68, 0.08);
}
.message-kicker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}
.interviewer-copy {
  margin: 0;
  color: #0f172a;
  line-height: 1.75;
  font-size: 16px;
  white-space: pre-wrap;
}
.candidate-message .message-bubble {
  color: #fff;
  background: linear-gradient(135deg, #2f7df6, #2366d9);
  border-color: transparent;
}
.candidate-message p {
  margin: 10px 0 0;
  line-height: 1.8;
  white-space: pre-wrap;
}
.candidate-message small {
  display: block;
  margin-top: 10px;
  color: rgba(255, 255, 255, 0.82);
  line-height: 1.7;
}
.submitted-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  font-weight: 700;
}
.submitted-head span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.rubric-collapse {
  margin-top: 10px;
}
.feedback-bubble {
  background: #f6fbff;
}
.final-bubble {
  background: #f0fdf4;
  border-color: #bbf7d0;
}
.answer-composer {
  position: sticky;
  bottom: 12px;
  z-index: 5;
  padding: 14px;
  border: 1px solid #cbd9eb;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 18px 44px rgba(28, 43, 68, 0.14);
  backdrop-filter: blur(14px);
}
.answer-composer :deep(.el-textarea__inner) {
  border-radius: 8px;
  line-height: 1.7;
}
.composer-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}
.composer-foot :deep(.el-button span) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
@media (max-width: 1024px) {
  .layout { grid-template-columns: 1fr; }
  .aside { position: static; }
}
@media (max-width: 640px) {
  .scoring-steps { grid-template-columns: 1fr; }
  .interview-quality-panel { grid-template-columns: 1fr; }
  .stage-head,
  .composer-foot {
    align-items: stretch;
    flex-direction: column;
  }
  .message-bubble {
    max-width: calc(100% - 46px);
  }
}
</style>
