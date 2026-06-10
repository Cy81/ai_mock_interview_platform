<script setup>
/**
 * 岗位匹配 Agent：
 *  - 选简历 + 调整 top_n，调用 /jobs/recommend；
 *  - 推荐卡片展示：百分比进度、匹配理由、技能差距、学习路径、知识库引用；
 *  - 显示 source 标签：llm（Agent）vs rule（兜底）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  BookOpen,
  RefreshCw,
  Sparkles,
  Target,
  TriangleAlert,
} from 'lucide-vue-next'
import { jobApi, resumeApi } from '@/api/modules'

const router = useRouter()

const resumes = ref([])
const jobs = ref([])
const result = ref(null)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')

const form = reactive({
  resume_id: '',
  top_n: 3,
})

const sourceMeta = {
  llm: { type: 'success', label: 'LLM Agent' },
  rule: { type: 'warning', label: '规则兜底' },
}

const selectedResume = computed(
  () => resumes.value.find((r) => r.id === form.resume_id) || null,
)

function unwrap(resp) {
  if (Array.isArray(resp)) return resp
  if (resp && Array.isArray(resp.items)) return resp.items
  return []
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [resumeData, jobData] = await Promise.all([
      resumeApi.list({ page: 1, page_size: 50 }),
      jobApi.list(),
    ])
    resumes.value = unwrap(resumeData).filter((r) => r.parse_status === 'parsed')
    jobs.value = unwrap(jobData)
    if (!form.resume_id && resumes.value.length) {
      form.resume_id = resumes.value[0].id
    }
  } catch (err) {
    error.value = err?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function recommend() {
  if (!form.resume_id) {
    ElMessage.warning('请先选择已解析的简历')
    return
  }
  submitting.value = true
  try {
    result.value = await jobApi.recommend({
      resume_id: Number(form.resume_id),
      top_n: Number(form.top_n),
    })
  } catch (err) {
    ElMessage.error(err?.message || '推荐失败')
  } finally {
    submitting.value = false
  }
}

function startInterview(rec) {
  router.push({
    path: '/interviews',
    query: { resume_id: form.resume_id, job_code: rec.code },
  })
}

onMounted(load)
</script>

<template>
  <div class="job-page job-match-studio">
    <section class="match-command-panel">
      <div class="match-copy">
        <p class="section-kicker">JOB MATCH AGENT</p>
        <h1>找到最值得模拟的岗位</h1>
        <p>选择一份已解析简历，Agent 会根据技能、项目经历和岗位能力模型推荐方向，并给出差距和学习路径。</p>
      </div>

      <el-alert v-if="error" type="error" :title="error" show-icon :closable="false" />

      <el-form label-position="top" class="match-form">
        <el-form-item label="选择简历">
          <el-select v-model="form.resume_id" class="full-control" placeholder="选择已解析的简历">
            <el-option
              v-for="r in resumes"
              :key="r.id"
              :value="r.id"
              :label="`#${r.id} ${r.filename}`"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="推荐数量">
          <el-input-number v-model="form.top_n" :min="1" :max="10" />
        </el-form-item>
        <el-button
          type="primary"
          size="large"
          :loading="submitting"
          :disabled="!form.resume_id"
          @click="recommend"
        >
          <Sparkles :size="14" /><span>生成岗位推荐</span>
        </el-button>
      </el-form>

      <div v-if="selectedResume" class="resume-tip">
        当前简历：<strong>{{ selectedResume.filename }}</strong>
        <span class="muted">· 目标岗位 {{ selectedResume.target_position || '未填写' }}</span>
      </div>

      <el-empty
        v-if="!loading && !resumes.length"
        description="暂无已解析的简历，先去上传一份"
      >
          <el-button type="primary" @click="router.push('/resumes')">去上传简历</el-button>
      </el-empty>
      <el-button text :icon="RefreshCw" :loading="loading" @click="load">刷新简历池</el-button>
    </section>

    <section v-if="submitting" class="recommendation-board loading-board">
      <el-skeleton :rows="6" animated />
    </section>

    <section v-else-if="result" class="recommendation-board">
      <div class="board-head">
        <div>
          <p class="section-kicker">RECOMMENDATIONS</p>
          <h2>推荐岗位</h2>
        </div>
        <span>{{ result.recommendations?.length || 0 }} 个方向</span>
      </div>

      <div class="job-card-grid">
        <article
          v-for="rec in result.recommendations"
          :key="rec.code"
          class="job-match-card"
        >
            <div class="rec-head">
              <div>
                <h4>{{ rec.title }}</h4>
                <small class="muted">{{ rec.code }}</small>
              </div>
              <el-tag :type="sourceMeta[rec.source]?.type || 'info'" size="small">
                {{ sourceMeta[rec.source]?.label || rec.source }}
              </el-tag>
            </div>

            <div class="match-score">
              <el-progress
                :percentage="Math.round(rec.match_score * 100)"
                :stroke-width="10"
                :status="rec.match_score >= 0.7 ? 'success' : rec.match_score >= 0.5 ? 'warning' : 'exception'"
              />
              <strong>{{ Math.round(rec.match_score * 100) }}%</strong>
            </div>

            <section>
              <h5><Target :size="14" /> 匹配依据</h5>
              <ul>
                <li v-for="r in rec.reasons" :key="r">{{ r }}</li>
                <li v-if="!rec.reasons?.length" class="muted">—</li>
              </ul>
            </section>

            <section>
              <h5><TriangleAlert :size="14" /> 技能差距</h5>
              <div class="gap-tags">
                <el-tag
                  v-for="g in rec.gaps"
                  :key="g"
                  size="small"
                  type="danger"
                  effect="plain"
                >
                  {{ g }}
                </el-tag>
                <span v-if="!rec.gaps?.length" class="muted">暂无明显差距</span>
              </div>
            </section>

            <section>
              <h5><BookOpen :size="14" /> 学习路径</h5>
              <ol>
                <li v-for="step in rec.suggested_learning_path" :key="step">{{ step }}</li>
                <li v-if="!rec.suggested_learning_path?.length" class="muted">—</li>
              </ol>
            </section>

            <el-collapse v-if="rec.knowledge_references?.length">
              <el-collapse-item :title="`知识库引用 (${rec.knowledge_references.length})`">
                <article
                  v-for="ref in rec.knowledge_references"
                  :key="ref.id"
                  class="kb-ref"
                >
                  <strong>{{ ref.title }}</strong>
                  <small class="muted">相关度 {{ ref.score?.toFixed?.(3) }}</small>
                  <p>{{ ref.content.slice(0, 220) }}{{ ref.content.length > 220 ? '...' : '' }}</p>
                </article>
              </el-collapse-item>
            </el-collapse>

            <el-button type="primary" plain class="cta-btn" @click="startInterview(rec)">
              用此岗位发起模拟面试
            </el-button>
        </article>
      </div>
    </section>

    <section v-else-if="!loading" class="recommendation-board empty-board">
      <el-empty description='选择简历后点击"生成推荐"，Agent 会基于双 RAG 给出 Top N 岗位' />
    </section>
  </div>
</template>

<style scoped>
.job-page { display: flex; flex-direction: column; gap: 16px; }
.match-command-panel,
.recommendation-board {
  border: 1px solid #dde6f1;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.93);
  box-shadow: 0 16px 38px rgba(28, 43, 68, 0.07);
}
.match-command-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 22px;
  align-items: end;
  padding: 26px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(255, 248, 235, 0.9)),
    radial-gradient(circle at 8% 10%, rgba(245, 158, 11, 0.16), transparent 18rem);
}
.section-kicker {
  margin: 0 0 8px;
  color: #6b7b91;
  font-size: 12px;
  font-weight: 800;
}
.match-copy h1 {
  margin: 0;
  color: #172033;
  font-size: 34px;
  line-height: 1.18;
}
.match-copy p:not(.section-kicker) {
  max-width: 680px;
  margin: 12px 0 0;
  color: #5f6f89;
  line-height: 1.8;
}
.match-form {
  padding: 18px;
  border: 1px solid #e1e8f2;
  border-radius: 8px;
  background: #fff;
}
.match-form .el-button {
  width: 100%;
  margin-top: 4px;
}
.match-form .el-button span {
  margin-left: 6px;
}
.full-control {
  width: 100%;
}
.resume-tip { margin-top: 12px; font-size: 13px; color: #475569; }
.muted { color: #94a3b8; }
.recommendation-board {
  padding: 22px;
}
.loading-board,
.empty-board {
  min-height: 240px;
}
.board-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.board-head h2 {
  margin: 0;
  color: #172033;
  font-size: 24px;
}
.board-head span {
  color: #6b7b91;
  font-size: 13px;
  font-weight: 800;
}
.job-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.job-match-card {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  padding: 18px;
  border: 1px solid #e1e8f2;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 10px 24px rgba(28, 43, 68, 0.05);
}
.rec-head { display: flex; justify-content: space-between; align-items: flex-start; }
.rec-head h4 { margin: 0; color: #0f172a; font-size: 16px; }
.match-score { display: flex; align-items: center; gap: 12px; margin: 12px 0 4px; }
.match-score :deep(.el-progress) { flex: 1; }
.match-score strong { font-size: 18px; color: #0f172a; min-width: 56px; text-align: right; }
.job-match-card section { margin-top: 14px; }
.job-match-card h5 {
  margin: 0 0 6px; color: #475569; font-size: 12px;
  display: flex; align-items: center; gap: 6px; letter-spacing: .5px;
}
.job-match-card ul, .job-match-card ol { margin: 0; padding-left: 20px; color: #1e293b; }
.job-match-card li { font-size: 13px; line-height: 1.7; }
.gap-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.kb-ref { padding: 8px 0; border-bottom: 1px dashed #e2e8f0; }
.kb-ref:last-child { border-bottom: 0; }
.kb-ref strong { color: #0f172a; font-size: 13px; }
.kb-ref small { margin-left: 8px; }
.kb-ref p { margin: 4px 0 0; color: #475569; font-size: 12px; line-height: 1.6; }
.cta-btn { margin-top: auto; width: 100%; }

@media (max-width: 1080px) {
  .match-command-panel,
  .job-card-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .match-command-panel,
  .recommendation-board {
    padding: 16px;
  }

  .match-copy h1 {
    font-size: 28px;
  }
}
</style>
