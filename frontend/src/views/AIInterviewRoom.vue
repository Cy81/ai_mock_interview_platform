<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  BrainCircuit,
  CheckCircle2,
  Circle,
  Clock,
  FileText,
  Flag,
  MessageSquarePlus,
  Pencil,
  RefreshCw,
  Save,
  SendHorizontal,
  Target,
  Trash2,
  TriangleAlert,
} from 'lucide-vue-next'
import { interviewApi, jobApi, resumeApi } from '@/api/modules'

const route = useRoute()
const router = useRouter()

const resumes = ref([])
const jobs = ref([])
const interviews = ref([])
const current = ref(null)
const resumeDetail = ref(null)
const currentIndex = ref(0)
const draftAnswer = ref('')
const elapsed = ref(0)
const bootLoading = ref(false)
const roomLoading = ref(false)
const creating = ref(false)
const submitting = ref(false)
const finishing = ref(false)
const autosaveState = ref('saved')
const transcriptRef = ref(null)
const feedbackByQuestion = reactive({})
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
  in_progress: { type: 'primary', label: '面试中' },
  scoring: { type: 'warning', label: '评分中' },
  completed: { type: 'success', label: '已完成' },
  failed: { type: 'danger', label: '失败' },
  cancelled: { type: 'info', label: '已取消' },
}

const questionTypeLabels = {
  technical: '技术深挖',
  project: '项目复盘',
  system_design: '系统设计',
  behavioral: '行为面试',
}

const difficultyLabels = {
  basic: '基础',
  intermediate: '进阶',
  advanced: '高阶',
}

let timer = null
let questionStartedAt = Date.now()
let streamController = null

const selectedResume = computed(
  () => resumes.value.find((item) => item.id === Number(form.resume_id)) || null,
)

const selectedJob = computed(
  () => jobs.value.find((item) => item.code === form.job_code) || null,
)

const parsedProfile = computed(() => resumeDetail.value?.parsed_profile || {})
const profileSkills = computed(() => normalizeList(parsedProfile.value.skills).slice(0, 10))
const profileProjects = computed(() => normalizeList(parsedProfile.value.projects).slice(0, 4))
const profileHighlights = computed(() => normalizeList(parsedProfile.value.highlights).slice(0, 5))
const profileRisks = computed(() => normalizeList(parsedProfile.value.risk_flags).slice(0, 4))

const profileSignals = computed(() => {
  const signals = []
  profileSkills.value.slice(0, 5).forEach((skill) => {
    signals.push({ type: 'skill', label: skill, note: `围绕 ${skill} 验证真实项目使用深度` })
  })
  profileProjects.value.slice(0, 3).forEach((project, index) => {
    signals.push({ type: 'project', label: `项目 ${index + 1}`, note: truncate(project, 58) })
  })
  profileRisks.value.slice(0, 2).forEach((risk) => {
    signals.push({ type: 'risk', label: '待澄清', note: risk })
  })
  return signals
})

const sortedQuestions = computed(() =>
  current.value ? [...(current.value.questions || [])].sort((a, b) => a.position - b.position) : [],
)

const answeredMap = computed(() => {
  const map = new Map()
  ;(current.value?.answers || []).forEach((answer) => map.set(answer.question_id, answer))
  return map
})

const currentQuestion = computed(() => sortedQuestions.value[currentIndex.value] || null)
const answeredCount = computed(
  () => sortedQuestions.value.filter((question) => answeredMap.value.has(question.id)).length,
)
const isReadonly = computed(() =>
  ['completed', 'cancelled', 'failed'].includes(current.value?.status),
)
const awaitingInterviewer = computed(() =>
  Object.values(feedbackByQuestion).some((feedback) => feedback?.loading),
)
const isCurrentAnswered = computed(
  () => !!currentQuestion.value && answeredMap.value.has(currentQuestion.value.id),
)
const canFinish = computed(
  () =>
    !!current.value &&
    ['created', 'in_progress'].includes(current.value.status) &&
    sortedQuestions.value.length > 0 &&
    answeredCount.value === sortedQuestions.value.length,
)
const composerDisabled = computed(
  () =>
    isReadonly.value ||
    submitting.value ||
    awaitingInterviewer.value ||
    !currentQuestion.value ||
    isCurrentAnswered.value ||
    canFinish.value,
)
const composerDisabledReason = computed(() => {
  if (isReadonly.value) return '这场面试已经结束，不能继续作答'
  if (submitting.value) return '正在提交你的回答'
  if (awaitingInterviewer.value) return 'AI 面试官正在追问，请稍等'
  if (!currentQuestion.value) return '暂无当前问题'
  if (isCurrentAnswered.value) return '当前问题已回答，等待下一轮'
  if (canFinish.value) return '全部问题已完成，可以生成报告'
  return '像真实面试一样直接回答，系统会自动保存草稿'
})

const currentTurnText = computed(() => {
  if (!current.value) return '选择简历和岗位后开始'
  if (canFinish.value) return '所有轮次已完成，等待生成评估报告'
  if (awaitingInterviewer.value) return 'AI 面试官正在根据你的回答追问'
  if (currentQuestion.value) {
    return `第 ${currentIndex.value + 1} / ${sortedQuestions.value.length} 轮`
  }
  return statusMeta[current.value.status]?.label || current.value.status
})

const followupStrategy = computed(() => {
  const question = currentQuestion.value
  if (!question) {
    return '面试开始后，我会先根据简历里的技能、项目和岗位目标建立追问路径。'
  }
  const evidence = questionEvidence(question)
  const risk = profileRisks.value[0]
  return [
    `本轮先验证「${question.skill || '核心能力'}」是否真的用在项目里。`,
    evidence ? `简历依据：${evidence}` : '',
    risk ? `需要澄清：${risk}` : '',
  ]
    .filter(Boolean)
    .join(' ')
})

const responseQualityHints = computed(() => [
  {
    key: 'scene',
    label: '说清场景',
    done: draftAnswer.value.trim().length >= 24,
  },
  {
    key: 'evidence',
    label: '给出证据',
    done: /(\d|%|用户|性能|耗时|成本|指标|上线|结果|日志|测试)/.test(draftAnswer.value),
  },
  {
    key: 'tradeoff',
    label: '说明取舍',
    done: /(因为|所以|但是|取舍|权衡|风险|方案|瓶颈|优化)/.test(draftAnswer.value),
  },
])

const conversationTurns = computed(() => {
  const turns = []
  if (!current.value) return turns

  turns.push({
    id: 'room-intro',
    role: 'interviewer',
    type: 'intro',
    eyebrow: 'AI 面试官',
    content: buildRoomIntro(),
  })

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
      eyebrow: `第 ${question.position} 轮 · ${questionTypeLabels[question.type] || question.type}`,
    })

    if (answer) {
      turns.push({
        id: `answer-${question.id}`,
        role: 'candidate',
        type: 'answer',
        answer,
        eyebrow: '候选人回答',
      })
    }

    if (feedback?.loading || feedback?.content || feedback?.error) {
      turns.push({
        id: `feedback-${question.id}`,
        role: 'interviewer',
        type: 'feedback',
        feedback,
        eyebrow: 'AI 面试官追问',
      })
    }
  })

  if (canFinish.value) {
    turns.push({
      id: 'room-finish',
      role: 'interviewer',
      type: 'finish',
      eyebrow: 'AI 面试官',
      content: '本场面试的问答已经完成。现在可以生成综合评估报告，我会汇总你的项目表达、技术深度、工程习惯和岗位匹配度。',
    })
  }

  return turns
})

function normalizeList(value) {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item || '').trim()).filter(Boolean)
}

function truncate(value, max = 80) {
  const text = String(value || '').trim()
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}

function unwrap(resp) {
  if (Array.isArray(resp)) return resp
  if (resp && Array.isArray(resp.items)) return resp.items
  return []
}

function formatElapsed(seconds) {
  const minutes = String(Math.floor(seconds / 60)).padStart(2, '0')
  const rest = String(seconds % 60).padStart(2, '0')
  return `${minutes}:${rest}`
}

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function questionEvidence(question) {
  const skill = String(question?.skill || '').toLowerCase()
  const matchedSkill = profileSkills.value.find((item) => item.toLowerCase() === skill)
  if (matchedSkill) return `简历技能「${matchedSkill}」`
  const project = profileProjects.value.find((item) => item.toLowerCase().includes(skill))
  if (project) return truncate(project, 90)
  return profileHighlights.value[0] || parsedProfile.value.summary || ''
}

function buildRoomIntro() {
  const name = parsedProfile.value.name || '你好'
  const job = current.value?.job_title || selectedJob.value?.title || '目标岗位'
  const skills = profileSkills.value.slice(0, 4).join('、') || '你的项目经历'
  return `${name}，我们开始 ${job} 模拟面试。我会优先围绕 ${skills} 展开，问题会逐步从简历事实、项目细节推进到工程取舍。`
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
  if (timer) window.clearInterval(timer)
  timer = null
}

function draftKey(interviewId, questionId) {
  return `aimi:room:${interviewId}:question:${questionId}`
}

function loadDraft() {
  if (!current.value || !currentQuestion.value) return
  const saved = localStorage.getItem(draftKey(current.value.id, currentQuestion.value.id))
  const submitted = answeredMap.value.get(currentQuestion.value.id)
  draftAnswer.value = saved ?? submitted?.answer ?? ''
}

function saveDraft() {
  if (!current.value || !currentQuestion.value) return
  autosaveState.value = 'saving'
  const key = draftKey(current.value.id, currentQuestion.value.id)
  if (draftAnswer.value) {
    localStorage.setItem(key, draftAnswer.value)
  } else {
    localStorage.removeItem(key)
  }
  window.setTimeout(() => {
    autosaveState.value = 'saved'
  }, 180)
}

watch(draftAnswer, saveDraft)

watch(
  () => form.resume_id,
  async (id) => {
    if (id && (!resumeDetail.value || resumeDetail.value.id !== Number(id))) {
      await loadResumeProfile(Number(id))
    }
  },
)

watch(
  () => route.params.id,
  async (id) => {
    if (id) {
      await loadInterview(Number(id))
    } else {
      current.value = null
      resetConversationFeedback()
      stopTimer()
    }
  },
)

function resetConversationFeedback() {
  Object.keys(feedbackByQuestion).forEach((key) => delete feedbackByQuestion[key])
  resetStream()
}

function resetScoringFeedback() {
  scoringFeedback.loading = false
  scoringFeedback.event = ''
  scoringFeedback.error = ''
  scoringFeedback.overallScore = null
}

function resetStream() {
  if (streamController) {
    streamController.abort()
    streamController = null
  }
}

function scrollTranscriptToBottom() {
  nextTick(() => {
    const el = transcriptRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function syncCurrentIndexFromAnswers() {
  const nextUnanswered = sortedQuestions.value.findIndex(
    (question) => !answeredMap.value.has(question.id),
  )
  currentIndex.value =
    nextUnanswered === -1 ? Math.max(sortedQuestions.value.length - 1, 0) : nextUnanswered
}

async function loadResumeProfile(resumeId) {
  if (!resumeId) return
  try {
    resumeDetail.value = await resumeApi.get(resumeId)
  } catch (err) {
    ElMessage.error(err?.message || '加载简历画像失败')
  }
}

async function loadRoomData() {
  bootLoading.value = true
  try {
    const [resumeData, jobData, interviewData] = await Promise.all([
      resumeApi.list({ page: 1, page_size: 50 }),
      jobApi.list(),
      interviewApi.list({ page: 1, page_size: 30 }),
    ])
    resumes.value = unwrap(resumeData).filter((item) => item.parse_status === 'parsed')
    jobs.value = unwrap(jobData)
    interviews.value = unwrap(interviewData)

    if (!form.resume_id && resumes.value.length) form.resume_id = resumes.value[0].id
    if (!form.job_code && jobs.value.length) form.job_code = jobs.value[0].code
    if (form.resume_id) await loadResumeProfile(Number(form.resume_id))

    if (route.params.id) await loadInterview(Number(route.params.id))
  } catch (err) {
    ElMessage.error(err?.message || '加载面试房间失败')
  } finally {
    bootLoading.value = false
  }
}

async function loadInterview(interviewId) {
  roomLoading.value = true
  try {
    current.value = await interviewApi.get(interviewId)
    form.resume_id = current.value.resume_id
    form.job_code = current.value.job_code
    await loadResumeProfile(current.value.resume_id)
    syncCurrentIndexFromAnswers()
    resetConversationFeedback()
    resetScoringFeedback()
    loadDraft()
    if (!isReadonly.value) startTimer()
    await nextTick()
    scrollTranscriptToBottom()
  } catch (err) {
    ElMessage.error(err?.message || '加载面试失败')
  } finally {
    roomLoading.value = false
  }
}

async function createInterview() {
  if (!form.resume_id || !form.job_code) {
    ElMessage.warning('请先选择简历和岗位')
    return
  }
  creating.value = true
  try {
    const created = await interviewApi.create({
      resume_id: Number(form.resume_id),
      job_code: form.job_code,
      question_count: Number(form.question_count),
      conversational: true,
      idempotency_key: `${form.resume_id}-${form.job_code}-${form.question_count}-${Date.now()}`,
    })
    interviews.value = [created, ...interviews.value.filter((item) => item.id !== created.id)]
    current.value = created
    currentIndex.value = 0
    resetConversationFeedback()
    resetScoringFeedback()
    await loadResumeProfile(created.resume_id)
    loadDraft()
    startTimer()
    ElMessage.success('AI 面试房间已生成')
    router.replace(`/interviews/${created.id}`)
  } catch (err) {
    ElMessage.error(err?.message || '创建面试失败')
  } finally {
    creating.value = false
  }
}

function openInterview(item) {
  router.push(`/interviews/${item.id}`)
}

async function removeInterview(item) {
  await ElMessageBox.confirm(`删除 #${item.id} ${item.job_title}？此操作不可恢复。`, '删除面试', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  try {
    await interviewApi.delete(item.id)
    interviews.value = interviews.value.filter((history) => history.id !== item.id)
    if (current.value?.id === item.id) {
      current.value = null
      router.replace('/interviews')
    }
    ElMessage.success('已删除')
  } catch (err) {
    ElMessage.error(err?.message || '删除失败')
  }
}

async function sendAnswer() {
  if (composerDisabled.value || !current.value || !currentQuestion.value) return
  const text = draftAnswer.value.trim()
  if (text.length < 5) {
    ElMessage.warning('回答至少 5 个字')
    return
  }
  submitting.value = true
  try {
    const duration = Date.now() - questionStartedAt
    const questionId = currentQuestion.value.id
    const turn = await interviewApi.turn(current.value.id, {
      question_id: questionId,
      answer: text,
      duration_ms: duration,
    })
    current.value = turn.interview
    localStorage.removeItem(draftKey(current.value.id, questionId))
    draftAnswer.value = ''
    await runFollowupStream(questionId)
    advanceToNextQuestion(questionId)
  } catch (err) {
    ElMessage.error(err?.message || '发送失败')
  } finally {
    submitting.value = false
  }
}

async function runFollowupStream(questionId) {
  if (!current.value || !questionId) return
  resetStream()
  const controller = new AbortController()
  streamController = controller
  feedbackByQuestion[questionId] = {
    loading: true,
    content: '',
    error: '',
  }
  scrollTranscriptToBottom()

  try {
    await interviewApi.stream(current.value.id, {
      params: { mode: 'followup', question_id: questionId },
      signal: controller.signal,
      onEvent: ({ event, data }) => {
        if (!feedbackByQuestion[questionId]) return
        if (event === 'followup_delta') {
          feedbackByQuestion[questionId].content += data.content || ''
          scrollTranscriptToBottom()
        }
        if (event === 'followup_done') {
          feedbackByQuestion[questionId].content =
            data.content || feedbackByQuestion[questionId].content
        }
        if (event === 'error') {
          feedbackByQuestion[questionId].error = data.message || 'AI 追问生成失败'
        }
      },
    })
  } catch (err) {
    if (err?.name !== 'AbortError') {
      feedbackByQuestion[questionId].error = err?.message || 'AI 追问生成失败'
    }
  } finally {
    if (feedbackByQuestion[questionId]) feedbackByQuestion[questionId].loading = false
    if (streamController === controller) streamController = null
  }
}

function advanceToNextQuestion(answeredQuestionId) {
  const answeredIndex = sortedQuestions.value.findIndex((question) => question.id === answeredQuestionId)
  const nextIndex = sortedQuestions.value.findIndex(
    (question, index) => index > answeredIndex && !answeredMap.value.has(question.id),
  )
  if (nextIndex === -1) {
    currentIndex.value = Math.max(answeredIndex, 0)
    stopTimer()
  } else {
    currentIndex.value = nextIndex
    startTimer()
    loadDraft()
  }
  scrollTranscriptToBottom()
}

async function finishInterview() {
  if (!current.value) return
  await ElMessageBox.confirm('确认结束面试并生成综合评估报告？', '完成面试', {
    confirmButtonText: '生成报告',
    cancelButtonText: '继续面试',
    type: 'warning',
  })
  finishing.value = true
  resetStream()
  scoringFeedback.loading = true
  scoringFeedback.event = 'scoring_started'
  scoringFeedback.error = ''
  scoringFeedback.overallScore = null
  const interviewId = current.value.id
  const controller = new AbortController()
  streamController = controller

  try {
    await interviewApi.stream(interviewId, {
      params: { mode: 'scoring' },
      signal: controller.signal,
      onEvent: ({ event, data }) => {
        scoringFeedback.event = event
        if (event === 'scoring_done') scoringFeedback.overallScore = data.overall_score ?? null
        if (event === 'report_ready') {
          scoringFeedback.overallScore =
            data.report?.overall_score ?? scoringFeedback.overallScore
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
    if (!scoringFeedback.error) {
      ElMessage.success('评分报告已生成')
      router.push(`/reports/${interviewId}`)
    }
  } catch (err) {
    if (err?.name !== 'AbortError') scoringFeedback.error = err?.message || '评分报告生成失败'
  } finally {
    scoringFeedback.loading = false
    finishing.value = false
    if (streamController === controller) streamController = null
  }
}

async function cancelInterview() {
  if (!current.value) return
  await ElMessageBox.confirm('确认取消这场面试？已提交的回答会保留。', '取消面试', {
    confirmButtonText: '取消面试',
    cancelButtonText: '继续',
    type: 'warning',
  })
  try {
    current.value = await interviewApi.cancel(current.value.id)
    ElMessage.success('已取消')
  } catch (err) {
    ElMessage.error(err?.message || '取消失败')
  }
}

function backToLobby() {
  current.value = null
  resetConversationFeedback()
  stopTimer()
  router.replace('/interviews')
}

onMounted(loadRoomData)

onUnmounted(() => {
  stopTimer()
  resetStream()
})
</script>

<template>
  <div class="ai-interview-room">
    <header class="room-hero">
      <div class="hero-copy">
        <p>AI INTERVIEW ROOM</p>
        <h1>根据简历展开的对话式面试</h1>
        <span>AI 会先读取候选人画像，再围绕项目、技能和岗位目标逐轮追问。</span>
      </div>
      <div class="hero-actions">
        <el-button plain :icon="RefreshCw" :loading="bootLoading" @click="loadRoomData">
          刷新数据
        </el-button>
        <el-button v-if="current" plain @click="backToLobby">返回候场区</el-button>
      </div>
    </header>

    <el-skeleton v-if="bootLoading" :rows="10" animated />

    <template v-else>
      <section v-if="!current" class="lobby-grid">
        <aside class="resume-insight-panel">
          <div class="panel-head">
            <FileText :size="17" />
            <strong>简历画像</strong>
          </div>

          <el-empty v-if="!resumes.length" description="暂无已解析简历">
            <el-button type="primary" @click="router.push('/resumes')">先上传简历</el-button>
          </el-empty>

          <template v-else>
            <el-select
              v-model="form.resume_id"
              class="full-control"
              placeholder="选择已解析简历"
            >
              <el-option
                v-for="resume in resumes"
                :key="resume.id"
                :value="resume.id"
                :label="`#${resume.id} ${resume.filename}`"
              />
            </el-select>

            <div class="profile-card">
              <p class="profile-name">
                {{ parsedProfile.name || '候选人' }}
                <span>{{ resumeDetail?.target_position || selectedResume?.target_position || '未填写目标岗位' }}</span>
              </p>
              <p class="profile-summary">
                {{ parsedProfile.summary || '简历解析完成后，AI 会在这里展示候选人画像摘要。' }}
              </p>
            </div>

            <div class="signal-list">
              <h3>面试信号</h3>
              <article
                v-for="signal in profileSignals"
                :key="`${signal.type}-${signal.label}-${signal.note}`"
                :class="`signal-${signal.type}`"
              >
                <strong>{{ signal.label }}</strong>
                <span>{{ signal.note }}</span>
              </article>
              <p v-if="!profileSignals.length" class="muted">简历画像信息较少，建议补充项目和技术栈。</p>
            </div>
          </template>
        </aside>

        <main class="lobby-start">
          <div class="start-panel">
            <div class="panel-head">
              <BrainCircuit :size="18" />
              <strong>创建一场真实面试</strong>
            </div>

            <el-form label-position="top">
              <el-form-item label="目标岗位">
                <el-select v-model="form.job_code" class="full-control" placeholder="选择岗位">
                  <el-option
                    v-for="job in jobs"
                    :key="job.code"
                    :value="job.code"
                    :label="job.title"
                  />
                </el-select>
              </el-form-item>

              <el-form-item label="面试轮次">
                <el-segmented v-model="form.question_count" :options="[4, 6, 8, 10]" />
              </el-form-item>
            </el-form>

            <div class="job-preview">
              <Target :size="18" />
              <div>
                <strong>{{ selectedJob?.title || '选择岗位后生成面试路径' }}</strong>
                <p>{{ selectedJob?.description || 'AI 会结合简历技能、项目经历和岗位能力模型生成问题。' }}</p>
              </div>
            </div>

            <el-button
              type="primary"
              size="large"
              :loading="creating"
              :disabled="!form.resume_id || !form.job_code"
              @click="createInterview"
            >
              <MessageSquarePlus :size="16" />
              开始 AI 面试
            </el-button>
          </div>
        </main>

        <aside class="history-panel">
          <div class="panel-head">
            <Clock :size="17" />
            <strong>最近面试</strong>
          </div>
          <el-empty v-if="!interviews.length" description="暂无面试记录" :image-size="72" />
          <ul v-else class="history-list">
            <li v-for="item in interviews" :key="item.id">
              <button type="button" @click="openInterview(item)">
                <strong>#{{ item.id }} {{ item.job_title }}</strong>
                <span>{{ formatDate(item.created_at) }}</span>
              </button>
              <el-tag :type="statusMeta[item.status]?.type" size="small">
                {{ statusMeta[item.status]?.label || item.status }}
              </el-tag>
              <el-button
                text
                type="danger"
                size="small"
                :icon="Trash2"
                @click="removeInterview(item)"
              />
            </li>
          </ul>
        </aside>
      </section>

      <section v-else class="focus-interview-layout">
        <div class="context-ribbon">
          <div>
            <span>当前候选人</span>
            <strong>{{ parsedProfile.name || '候选人' }}</strong>
            <small>{{ current.job_title }}</small>
          </div>
          <div>
            <span>简历依据</span>
            <strong>{{ profileSkills.slice(0, 3).join(' / ') || '等待识别' }}</strong>
            <small>{{ profileProjects[0] ? truncate(profileProjects[0], 42) : '未识别到项目线索' }}</small>
          </div>
          <div>
            <span>本轮策略</span>
            <strong>{{ currentQuestion?.skill || '核心能力' }}</strong>
            <small>{{ truncate(followupStrategy, 56) }}</small>
          </div>
        </div>

        <div class="room-grid compact-room-grid">
          <aside class="resume-insight-panel">
          <div class="panel-head">
            <FileText :size="17" />
            <strong>简历依据</strong>
          </div>

          <div class="profile-card compact">
            <p class="profile-name">
              {{ parsedProfile.name || '候选人' }}
              <span>{{ current.job_title }}</span>
            </p>
            <p class="profile-summary">{{ parsedProfile.summary || '暂无简历摘要' }}</p>
          </div>

          <section class="mini-section">
            <h3>核心技能</h3>
            <div class="tag-cloud">
              <el-tag v-for="skill in profileSkills" :key="skill" size="small" effect="plain">
                {{ skill }}
              </el-tag>
              <span v-if="!profileSkills.length" class="muted">未识别到技能</span>
            </div>
          </section>

          <section class="mini-section">
            <h3>项目线索</h3>
            <ul>
              <li v-for="project in profileProjects" :key="project">{{ truncate(project, 96) }}</li>
              <li v-if="!profileProjects.length" class="muted">未识别到项目经历</li>
            </ul>
          </section>

          <section v-if="profileRisks.length" class="mini-section risk-box">
            <h3><TriangleAlert :size="14" /> 待澄清点</h3>
            <p v-for="risk in profileRisks" :key="risk">{{ risk }}</p>
          </section>
          </aside>

          <main class="interview-stage" v-loading="roomLoading">
          <header class="stage-bar">
            <div>
              <p>#{{ current.id }} · {{ current.job_title }}</p>
              <h2>{{ currentTurnText }}</h2>
            </div>
            <div class="stage-metrics">
              <span><Clock :size="14" /> {{ formatElapsed(elapsed) }}</span>
              <el-tag :type="statusMeta[current.status]?.type">
                {{ statusMeta[current.status]?.label || current.status }}
              </el-tag>
            </div>
          </header>

          <div class="progress-strip">
            <button
              v-for="(question, index) in sortedQuestions"
              :key="question.id"
              type="button"
              class="progress-step"
              :class="{ active: index === currentIndex, done: answeredMap.has(question.id) }"
              @click="currentIndex = index; loadDraft(); scrollTranscriptToBottom()"
            >
              <CheckCircle2 v-if="answeredMap.has(question.id)" :size="14" />
              <Circle v-else :size="14" />
              <span>{{ index + 1 }}</span>
            </button>
            <strong>{{ answeredCount }} / {{ sortedQuestions.length }}</strong>
          </div>

          <section ref="transcriptRef" class="interview-transcript">
            <article
              v-for="turn in conversationTurns"
              :key="turn.id"
              class="message-row"
              :class="turn.role === 'candidate' ? 'candidate-row' : 'interviewer-row'"
            >
              <div class="avatar">{{ turn.role === 'candidate' ? '我' : 'AI' }}</div>
              <div class="message-bubble">
                <div class="message-kicker">
                  <span>{{ turn.eyebrow }}</span>
                  <div v-if="turn.question" class="question-tags">
                    <el-tag size="small" type="primary">
                      {{ questionTypeLabels[turn.question.type] || turn.question.type }}
                    </el-tag>
                    <el-tag size="small" type="warning">
                      {{ difficultyLabels[turn.question.difficulty] || turn.question.difficulty }}
                    </el-tag>
                  </div>
                </div>

                <template v-if="turn.type === 'question'">
                  <p class="question-copy">{{ turn.question.question }}</p>
                  <div class="evidence-line">
                    <strong>追问依据</strong>
                    <span>{{ questionEvidence(turn.question) || '结合岗位能力模型继续验证' }}</span>
                  </div>
                  <ul v-if="turn.question.rubric?.length" class="rubric-list">
                    <li v-for="item in turn.question.rubric" :key="item">{{ item }}</li>
                  </ul>
                </template>

                <template v-else-if="turn.type === 'answer'">
                  <p>{{ turn.answer.answer }}</p>
                  <small v-if="turn.answer.comment">{{ turn.answer.comment }}</small>
                </template>

                <template v-else-if="turn.type === 'feedback'">
                  <p v-if="turn.feedback.content">{{ turn.feedback.content }}</p>
                  <p v-else-if="turn.feedback.loading" class="thinking">正在根据你的回答组织追问...</p>
                  <p v-if="turn.feedback.error" class="error-text">{{ turn.feedback.error }}</p>
                </template>

                <template v-else>
                  <p>{{ turn.content }}</p>
                </template>
              </div>
            </article>
          </section>

          <section class="candidate-composer">
            <div class="composer-head">
              <span><Pencil :size="14" /> 回答 AI 面试官</span>
              <span class="muted">
                {{ draftAnswer.length }} / 8000 · {{ autosaveState === 'saving' ? '保存中' : '已保存' }}
              </span>
            </div>
            <el-input
              v-model="draftAnswer"
              type="textarea"
              :rows="5"
              maxlength="8000"
              placeholder="直接像真实面试一样回答。建议说清背景、你的动作、结果和取舍。"
              :disabled="composerDisabled"
              @keydown.ctrl.enter.prevent="sendAnswer"
              @keydown.meta.enter.prevent="sendAnswer"
            />
            <div class="composer-foot">
              <p class="muted"><Save :size="13" /> {{ composerDisabledReason }}</p>
              <el-button
                type="primary"
                :loading="submitting || awaitingInterviewer"
                :disabled="composerDisabled"
                @click="sendAnswer"
              >
                <SendHorizontal :size="15" />
                发送回答
              </el-button>
            </div>
          </section>
          </main>

          <aside class="coach-panel">
          <div class="panel-head">
            <BrainCircuit :size="17" />
            <strong>AI 追问策略</strong>
          </div>
          <p class="strategy-copy">{{ followupStrategy }}</p>

          <section class="mini-section">
            <h3>回答质量检查</h3>
            <div class="quality-list">
              <span
                v-for="item in responseQualityHints"
                :key="item.key"
                :class="{ done: item.done }"
              >
                <CheckCircle2 v-if="item.done" :size="13" />
                <Circle v-else :size="13" />
                {{ item.label }}
              </span>
            </div>
          </section>

          <section class="score-panel" v-if="scoringFeedback.loading || scoringFeedback.event || scoringFeedback.error">
            <h3>报告生成</h3>
            <p>{{ scoringFeedback.error || scoringFeedback.event || '准备评分' }}</p>
            <strong v-if="scoringFeedback.overallScore != null">
              {{ Math.round(scoringFeedback.overallScore) }} 分
            </strong>
          </section>

          <div class="room-actions">
            <el-button
              type="success"
              :icon="Flag"
              :loading="finishing || scoringFeedback.loading"
              :disabled="!canFinish || scoringFeedback.loading"
              @click="finishInterview"
            >
              生成报告
            </el-button>
            <el-button
              v-if="['created', 'in_progress'].includes(current.status)"
              plain
              @click="cancelInterview"
            >
              取消面试
            </el-button>
          </div>
          </aside>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.ai-interview-room {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.room-hero {
  min-height: 132px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
  border: 1px solid #d8e2ef;
  border-radius: 8px;
  color: #172033;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(241, 247, 255, 0.92)),
    linear-gradient(90deg, rgba(45, 127, 249, 0.08), rgba(20, 184, 166, 0.08));
}

.hero-copy p {
  margin: 0 0 8px;
  color: #2f7df6;
  font-size: 12px;
  font-weight: 800;
}

.hero-copy h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.15;
}

.hero-copy span {
  display: block;
  margin-top: 10px;
  color: #5f6f89;
  font-size: 14px;
}

.hero-actions {
  display: flex;
  gap: 10px;
}

.lobby-grid,
.room-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 280px;
  gap: 16px;
  align-items: start;
}

.focus-interview-layout {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.context-ribbon {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 12px;
  border: 1px solid #d8e2ef;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 12px 28px rgba(23, 32, 51, 0.05);
}

.context-ribbon div {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fbff;
}

.context-ribbon span,
.context-ribbon strong,
.context-ribbon small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-ribbon span {
  color: #8a97aa;
  font-size: 11px;
  font-weight: 800;
}

.context-ribbon strong {
  margin-top: 3px;
  color: #172033;
  font-size: 14px;
}

.context-ribbon small {
  margin-top: 4px;
  color: #5f6f89;
  font-size: 12px;
}

.compact-room-grid {
  grid-template-columns: 230px minmax(0, 1fr) 250px;
}

.resume-insight-panel,
.lobby-start,
.history-panel,
.interview-stage,
.coach-panel {
  border: 1px solid #d8e2ef;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 16px 36px rgba(23, 32, 51, 0.06);
}

.resume-insight-panel,
.history-panel,
.coach-panel {
  position: sticky;
  top: 92px;
  padding: 16px;
}

.lobby-start,
.interview-stage {
  padding: 18px;
}

.panel-head {
  min-height: 28px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #172033;
  font-size: 14px;
  font-weight: 800;
}

.full-control {
  width: 100%;
}

.profile-card {
  margin-top: 14px;
  padding: 14px;
  border: 1px solid #e1e8f2;
  border-radius: 8px;
  background: #f8fbff;
}

.profile-card.compact {
  margin-top: 12px;
}

.profile-name {
  margin: 0;
  color: #172033;
  font-size: 16px;
  font-weight: 800;
}

.profile-name span {
  display: block;
  margin-top: 3px;
  color: #5f6f89;
  font-size: 12px;
  font-weight: 700;
}

.profile-summary {
  margin: 10px 0 0;
  color: #4b5f78;
  font-size: 13px;
  line-height: 1.7;
}

.signal-list,
.mini-section {
  margin-top: 16px;
}

.signal-list h3,
.mini-section h3 {
  margin: 0 0 8px;
  color: #4b5f78;
  font-size: 12px;
  font-weight: 800;
}

.signal-list article {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
  border: 1px solid #e1e8f2;
  border-radius: 8px;
  background: #fff;
}

.signal-list article + article {
  margin-top: 8px;
}

.signal-list strong {
  color: #172033;
  font-size: 13px;
}

.signal-list span {
  color: #5f6f89;
  font-size: 12px;
  line-height: 1.6;
}

.signal-skill {
  border-left: 3px solid #2f7df6 !important;
}

.signal-project {
  border-left: 3px solid #14b8a6 !important;
}

.signal-risk {
  border-left: 3px solid #f59e0b !important;
}

.start-panel {
  min-height: 480px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.job-preview {
  display: flex;
  gap: 12px;
  padding: 14px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #eff6ff;
}

.job-preview strong {
  color: #1d4ed8;
}

.job-preview p {
  margin: 6px 0 0;
  color: #4b5f78;
  line-height: 1.7;
  font-size: 13px;
}

.history-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-list li {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 8px;
  align-items: center;
  padding: 10px;
  border: 1px solid #e1e8f2;
  border-radius: 8px;
  background: #fff;
}

.history-list button {
  min-width: 0;
  padding: 0;
  border: 0;
  text-align: left;
  background: transparent;
  cursor: pointer;
}

.history-list strong,
.history-list span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-list strong {
  color: #172033;
  font-size: 13px;
}

.history-list span {
  margin-top: 3px;
  color: #8a97aa;
  font-size: 12px;
}

.stage-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid #e1e8f2;
}

.stage-bar p {
  margin: 0 0 4px;
  color: #8a97aa;
  font-size: 12px;
  font-weight: 800;
}

.stage-bar h2 {
  margin: 0;
  color: #172033;
  font-size: 20px;
}

.stage-metrics {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stage-metrics span {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  border: 1px solid #e1e8f2;
  border-radius: 8px;
  color: #4b5f78;
  background: #fff;
  font-size: 12px;
  font-weight: 800;
}

.progress-strip {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  overflow-x: auto;
}

.progress-step {
  width: 40px;
  height: 34px;
  flex: 0 0 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border: 1px solid #d8e2ef;
  border-radius: 8px;
  color: #64748b;
  background: #f8fbff;
  cursor: pointer;
}

.progress-step.active {
  color: #1d4ed8;
  border-color: #93c5fd;
  background: #eff6ff;
}

.progress-step.done {
  color: #0f766e;
  border-color: #99f6e4;
  background: #ecfdf5;
}

.progress-strip strong {
  margin-left: auto;
  color: #4b5f78;
  font-size: 12px;
}

.interview-transcript {
  height: min(58vh, 650px);
  min-height: 430px;
  margin-top: 14px;
  padding: 4px 4px 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.candidate-row {
  flex-direction: row-reverse;
}

.avatar {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #172033;
  background: #fff;
  border: 2px solid #172033;
  font-size: 12px;
  font-weight: 900;
}

.candidate-row .avatar {
  color: #fff;
  border-color: transparent;
  background: linear-gradient(135deg, #2f7df6, #14b8a6);
}

.message-bubble {
  max-width: min(720px, calc(100% - 50px));
  padding: 14px 16px;
  border: 1px solid #d8e2ef;
  border-radius: 8px;
  background: #fff;
}

.candidate-row .message-bubble {
  color: #fff;
  border-color: transparent;
  background: #1d4ed8;
}

.message-kicker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.candidate-row .message-kicker {
  color: rgba(255, 255, 255, 0.82);
}

.question-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.message-bubble p,
.question-copy {
  margin: 0;
  line-height: 1.75;
  font-size: 14px;
  white-space: pre-wrap;
}

.question-copy {
  color: #172033;
  font-size: 16px;
}

.evidence-line {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 12px;
  padding: 10px;
  border-radius: 8px;
  color: #4b5f78;
  background: #f8fbff;
  font-size: 12px;
}

.evidence-line strong {
  color: #1d4ed8;
}

.rubric-list {
  margin: 10px 0 0;
  padding-left: 18px;
  color: #5f6f89;
  font-size: 12px;
  line-height: 1.7;
}

.candidate-row small {
  display: block;
  margin-top: 8px;
  color: rgba(255, 255, 255, 0.78);
}

.thinking {
  color: #8a97aa;
}

.candidate-composer {
  position: sticky;
  bottom: 12px;
  z-index: 5;
  padding: 14px;
  border: 1px solid #cbd9eb;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 18px 40px rgba(23, 32, 51, 0.14);
  backdrop-filter: blur(14px);
}

.composer-head,
.composer-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.composer-head {
  margin-bottom: 8px;
  color: #4b5f78;
  font-size: 12px;
  font-weight: 800;
}

.composer-foot {
  margin-top: 10px;
}

.composer-foot p {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0;
}

.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.mini-section ul {
  margin: 0;
  padding-left: 18px;
  color: #4b5f78;
  font-size: 12px;
  line-height: 1.7;
}

.risk-box {
  padding: 12px;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  background: #fff7ed;
}

.risk-box h3 {
  display: flex;
  align-items: center;
  gap: 5px;
  color: #9a3412;
}

.risk-box p {
  margin: 6px 0 0;
  color: #7c2d12;
  font-size: 12px;
  line-height: 1.6;
}

.strategy-copy {
  margin: 12px 0 0;
  color: #4b5f78;
  font-size: 13px;
  line-height: 1.75;
}

.quality-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.quality-list span {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  border: 1px solid #d8e2ef;
  border-radius: 8px;
  color: #64748b;
  background: #f8fbff;
  font-size: 12px;
  font-weight: 800;
}

.quality-list span.done {
  color: #0f766e;
  border-color: #99f6e4;
  background: #ecfdf5;
}

.score-panel {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #eff6ff;
}

.score-panel h3 {
  margin: 0 0 6px;
  color: #1d4ed8;
  font-size: 12px;
}

.score-panel p {
  margin: 0;
  color: #4b5f78;
  font-size: 12px;
}

.score-panel strong {
  display: block;
  margin-top: 8px;
  color: #1d4ed8;
  font-size: 20px;
}

.room-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 18px;
}

.muted {
  color: #8a97aa;
  font-size: 12px;
}

.error-text {
  color: #b91c1c;
}

@media (max-width: 1180px) {
  .lobby-grid,
  .room-grid {
    grid-template-columns: 260px minmax(0, 1fr);
  }

  .history-panel,
  .coach-panel {
    position: static;
    grid-column: 1 / -1;
  }

  .context-ribbon {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 820px) {
  .room-hero,
  .stage-bar,
  .composer-foot {
    align-items: stretch;
    flex-direction: column;
  }

  .lobby-grid,
  .room-grid {
    grid-template-columns: 1fr;
  }

  .resume-insight-panel {
    position: static;
  }

  .interview-transcript {
    height: auto;
    max-height: none;
  }
}
</style>
