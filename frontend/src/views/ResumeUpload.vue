<script setup>
/**
 * 简历解析：
 *  - el-upload 拖拽 / 点击，上传前校验类型与大小（≤10MB）；
 *  - 上传走独立 uploadApi，进度条由 onUploadProgress 驱动；
 *  - 文本粘贴入口走 /resumes，至少 20 字；
 *  - 列表分页走后端 Page[T]，点击行打开抽屉看 parsed_profile 全文。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FileText, Upload as UploadIcon, RefreshCw, Trash2 } from 'lucide-vue-next'
import { resumeApi } from '@/api/modules'

const ACCEPT = '.pdf,.docx,.doc,.txt,.md'
const MAX_BYTES = 10 * 1024 * 1024

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const uploadProgress = ref(0)
const detail = ref(null)
const drawerVisible = ref(false)

const text = reactive({
  filename: 'manual-input.txt',
  target_position: '',
  text: '',
  submitting: false,
})
const upload = reactive({
  target_position: '',
})

const statusMeta = {
  pending: { type: 'info', label: '排队中' },
  parsing: { type: 'warning', label: '解析中' },
  parsed: { type: 'success', label: '已解析' },
  failed: { type: 'danger', label: '失败' },
}

const textValid = computed(() => text.text.trim().length >= 20)

async function load(targetPage = page.value) {
  loading.value = true
  try {
    const resp = await resumeApi.list({ page: targetPage, page_size: pageSize.value })
    list.value = resp.items || []
    total.value = resp.total || 0
    page.value = resp.page || targetPage
  } catch (err) {
    ElMessage.error(err?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function beforeUpload(file) {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!['pdf', 'docx', 'doc', 'txt', 'md'].includes(ext)) {
    ElMessage.error('仅支持 PDF / DOCX / TXT / MD')
    return false
  }
  if (file.size > MAX_BYTES) {
    ElMessage.error('文件不能超过 10MB')
    return false
  }
  return true
}

async function customUpload({ file }) {
  uploadProgress.value = 0
  const data = new FormData()
  data.append('file', file)
  if (upload.target_position) data.append('target_position', upload.target_position)
  try {
    await resumeApi.upload(data, (ratio) => (uploadProgress.value = Math.round(ratio * 100)))
    ElMessage.success('上传完成，已进入解析队列')
    await load(1)
  } catch (err) {
    ElMessage.error(err?.message || '上传失败')
  } finally {
    uploadProgress.value = 0
  }
}

async function submitText() {
  if (!textValid.value) {
    ElMessage.warning('简历内容至少 20 个字符')
    return
  }
  text.submitting = true
  try {
    await resumeApi.createText({
      filename: text.filename,
      target_position: text.target_position || undefined,
      text: text.text,
    })
    ElMessage.success('文本简历已保存')
    text.text = ''
    await load(1)
  } catch (err) {
    ElMessage.error(err?.message || '保存失败')
  } finally {
    text.submitting = false
  }
}

async function openDetail(row) {
  try {
    detail.value = await resumeApi.get(row.id)
    drawerVisible.value = true
  } catch (err) {
    ElMessage.error(err?.message || '获取简历详情失败')
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`确定删除 #${row.id} ${row.filename}？`, '删除简历', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  try {
    await resumeApi.delete(row.id)
    ElMessage.success('已删除')
    await load(page.value)
  } catch (err) {
    ElMessage.error(err?.message || '删除失败')
  }
}

function scrollToUpload() {
  document.querySelector('.upload-dropzone-panel')?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

onMounted(() => load(1))
</script>

<template>
  <div class="resume-page">
    <section class="resume-command-center">
      <div class="resume-hero-copy">
        <p class="section-kicker">RESUME WORKSPACE</p>
        <h1>先让 AI 读懂你的简历</h1>
        <p>上传 PDF 或粘贴文本后，系统会持久化简历、解析技能与项目经历，并用于后续岗位匹配和面试追问。</p>
      </div>

      <div class="resume-timeline">
        <span class="active">上传</span>
        <span :class="{ active: list.length }">解析</span>
        <span :class="{ active: list.some((item) => item.parse_status === 'parsed') }">匹配岗位</span>
        <span>开始面试</span>
      </div>
    </section>

    <section class="resume-workspace-grid">
      <article class="upload-dropzone-panel">
        <div class="card-head">
          <h3><UploadIcon :size="16" /> 上传简历文件</h3>
          <span class="muted">PDF / DOCX / TXT / MD · ≤10MB</span>
        </div>
          <el-form label-position="top">
            <el-form-item label="目标岗位（可选）">
              <el-input
                v-model="upload.target_position"
                placeholder="如：AI 应用工程师 / 后端开发"
                maxlength="120"
              />
            </el-form-item>

            <el-upload
              drag
              :accept="ACCEPT"
              :show-file-list="false"
              :before-upload="beforeUpload"
              :http-request="customUpload"
            >
              <UploadIcon :size="32" class="up-icon" />
              <div class="up-text">点击或拖拽文件到此处</div>
              <div class="up-tip">支持 PDF / DOCX / TXT / MD，最大 10MB</div>
            </el-upload>

            <el-progress
              v-if="uploadProgress > 0"
              :percentage="uploadProgress"
              status="success"
              style="margin-top: 12px"
            />
          </el-form>
      </article>

      <article class="paste-resume-panel">
        <div class="card-head">
          <h3><FileText :size="16" /> 粘贴文本简历</h3>
          <span class="muted">{{ text.text.trim().length }} / 200000 字</span>
        </div>
          <el-form label-position="top">
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="文件名">
                  <el-input v-model="text.filename" maxlength="255" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="目标岗位（可选）">
                  <el-input v-model="text.target_position" maxlength="120" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="简历内容">
              <el-input
                v-model="text.text"
                type="textarea"
                :rows="8"
                placeholder="粘贴整份简历文本（不少于 20 字）"
                maxlength="200000"
              />
            </el-form-item>
            <el-button
              type="primary"
              :disabled="!textValid"
              :loading="text.submitting"
              @click="submitText"
            >
              保存并解析
            </el-button>
          </el-form>
      </article>
    </section>

    <section class="resume-library">
      <div class="card-head">
        <div>
          <p class="section-kicker">RESUME LIBRARY</p>
          <h3>简历档案</h3>
        </div>
        <el-button text :icon="RefreshCw" :loading="loading" @click="load(page)">刷新</el-button>
      </div>

      <div v-loading="loading" class="parsed-resume-grid">
        <article
          v-for="row in list"
          :key="row.id"
          class="resume-file-card"
          @click="openDetail(row)"
        >
          <div class="file-card-head">
            <FileText :size="18" />
            <el-tag :type="statusMeta[row.parse_status]?.type || 'info'" size="small">
              {{ statusMeta[row.parse_status]?.label || row.parse_status }}
            </el-tag>
          </div>
          <strong>#{{ row.id }} {{ row.filename }}</strong>
          <p>{{ row.target_position || '未填写目标岗位' }}</p>
          <small>{{ new Date(row.created_at).toLocaleString() }}</small>
          <div class="file-card-actions">
            <el-button type="primary" plain size="small" @click.stop="openDetail(row)">
              查看解析
            </el-button>
            <el-button type="danger" text size="small" :icon="Trash2" @click.stop="remove(row)">
              删除
            </el-button>
          </div>
        </article>

        <el-empty v-if="!list.length && !loading" description="尚未上传简历">
          <el-button type="primary" @click="scrollToUpload">上传第一份简历</el-button>
        </el-empty>
      </div>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          background
          layout="total, sizes, prev, pager, next"
          @current-change="load"
          @size-change="() => load(1)"
        />
      </div>
    </section>

    <el-drawer
      v-model="drawerVisible"
      :title="detail ? `#${detail.id} ${detail.filename}` : '简历详情'"
      direction="rtl"
      size="540px"
    >
      <div v-if="detail" class="detail">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="目标岗位">{{ detail.target_position || '—' }}</el-descriptions-item>
          <el-descriptions-item label="MIME">{{ detail.mime_type || '—' }}</el-descriptions-item>
          <el-descriptions-item label="文件大小">
            {{ (detail.file_size / 1024).toFixed(1) }} KB
          </el-descriptions-item>
          <el-descriptions-item label="解析状态">
            <el-tag :type="statusMeta[detail.parse_status]?.type">
              {{ statusMeta[detail.parse_status]?.label }}
            </el-tag>
            <span v-if="detail.parse_error" class="error-text">
              · {{ detail.parse_error }}
            </span>
          </el-descriptions-item>
        </el-descriptions>

        <h4 class="mt">解析摘要</h4>
        <p class="muted">{{ detail.parsed_profile?.summary || '暂无摘要' }}</p>

        <h4>识别技能</h4>
        <div class="tags">
          <el-tag
            v-for="skill in detail.parsed_profile?.skills || []"
            :key="skill"
            size="small"
            effect="plain"
          >
            {{ skill }}
          </el-tag>
          <span v-if="!detail.parsed_profile?.skills?.length" class="muted">未提取到技能</span>
        </div>

        <h4>项目经历</h4>
        <ul v-if="detail.parsed_profile?.projects?.length" class="muted">
          <li v-for="(p, idx) in detail.parsed_profile.projects" :key="idx">{{ p }}</li>
        </ul>
        <p v-else class="muted">未识别到项目经历</p>

        <h4>原始文本（截取）</h4>
        <pre class="raw">{{ (detail.raw_text || '').slice(0, 1500) }}{{ (detail.raw_text || '').length > 1500 ? '...' : '' }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.resume-page { display: flex; flex-direction: column; gap: 16px; }
.resume-command-center,
.upload-dropzone-panel,
.paste-resume-panel,
.resume-library {
  border: 1px solid #dde6f1;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 16px 38px rgba(28, 43, 68, 0.07);
}
.resume-command-center {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
  gap: 18px;
  align-items: center;
  padding: 26px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.96), rgba(239, 247, 255, 0.9)),
    radial-gradient(circle at 88% 20%, rgba(20, 184, 166, 0.18), transparent 16rem);
}
.section-kicker {
  margin: 0 0 8px;
  color: #6b7b91;
  font-size: 12px;
  font-weight: 800;
}
.resume-hero-copy h1 {
  margin: 0;
  color: #172033;
  font-size: 34px;
  line-height: 1.18;
}
.resume-hero-copy p:not(.section-kicker) {
  max-width: 680px;
  margin: 12px 0 0;
  color: #5f6f89;
  line-height: 1.8;
}
.resume-timeline {
  display: grid;
  gap: 9px;
}
.resume-timeline span {
  min-height: 38px;
  display: flex;
  align-items: center;
  padding: 0 12px;
  border: 1px solid #d9e4f1;
  border-radius: 8px;
  color: #6b7b91;
  background: #fff;
  font-size: 13px;
  font-weight: 800;
}
.resume-timeline span.active {
  color: #0f766e;
  border-color: #99f6e4;
  background: #ecfdf5;
}
.resume-workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
  gap: 16px;
}
.upload-dropzone-panel,
.paste-resume-panel,
.resume-library {
  padding: 20px;
}
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.card-head h3 { margin: 0; font-size: 15px; color: #0f172a; display: flex; align-items: center; gap: 6px; }
.muted { color: #94a3b8; font-size: 12px; }
.up-icon { color: #94a3b8; }
.up-text { color: #1e293b; font-size: 14px; margin-top: 8px; }
.up-tip { color: #94a3b8; font-size: 12px; margin-top: 4px; }
.resume-library {
  margin-top: 4px;
}
.parsed-resume-grid {
  min-height: 180px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.resume-file-card {
  min-height: 178px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 15px;
  border: 1px solid #e1e8f2;
  border-radius: 8px;
  background: #f8fbff;
  cursor: pointer;
  transition:
    transform 0.16s ease,
    border-color 0.16s ease,
    box-shadow 0.16s ease;
}
.resume-file-card:hover {
  transform: translateY(-2px);
  border-color: #bad4ff;
  box-shadow: 0 12px 24px rgba(28, 43, 68, 0.09);
}
.file-card-head,
.file-card-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.resume-file-card strong {
  color: #172033;
  line-height: 1.45;
}
.resume-file-card p {
  margin: 0;
  color: #5f6f89;
  font-size: 13px;
}
.resume-file-card small {
  margin-top: auto;
  color: #8a97aa;
  font-size: 12px;
}
.pager { display: flex; justify-content: flex-end; margin-top: 14px; }
.detail h4 { margin: 18px 0 8px; color: #0f172a; font-size: 14px; }
.detail .tags { display: flex; flex-wrap: wrap; gap: 6px; }
.detail .raw {
  background: #0f172a; color: #cbd5e1; padding: 12px; border-radius: 8px;
  font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
  max-height: 280px; overflow: auto;
}
.error-text { color: #dc2626; font-size: 12px; margin-left: 8px; }

@media (max-width: 980px) {
  .resume-command-center,
  .resume-workspace-grid,
  .parsed-resume-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .resume-command-center,
  .upload-dropzone-panel,
  .paste-resume-panel,
  .resume-library {
    padding: 16px;
  }

  .resume-hero-copy h1 {
    font-size: 28px;
  }
}
</style>
