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

onMounted(() => load(1))
</script>

<template>
  <div class="resume-page">
    <el-row :gutter="16">
      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <h3><UploadIcon :size="16" /> 上传简历文件</h3>
              <span class="muted">PDF / DOCX / TXT / MD · ≤10MB</span>
            </div>
          </template>
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
        </el-card>
      </el-col>

      <el-col :xs="24" :md="12">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <h3><FileText :size="16" /> 粘贴文本简历</h3>
              <span class="muted">{{ text.text.trim().length }} / 200000 字</span>
            </div>
          </template>
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
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="mt">
      <template #header>
        <div class="card-head">
          <h3>简历档案</h3>
          <el-button text :icon="RefreshCw" :loading="loading" @click="load(page)">刷新</el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="list" stripe @row-click="openDetail">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="filename" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column prop="target_position" label="目标岗位" width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.target_position || '—' }}</template>
        </el-table-column>
        <el-table-column label="解析状态" width="120">
          <template #default="{ row }">
            <el-tag
              :type="statusMeta[row.parse_status]?.type || 'info'"
              size="small"
            >
              {{ statusMeta[row.parse_status]?.label || row.parse_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              type="danger"
              size="small"
              text
              :icon="Trash2"
              @click.stop="remove(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="尚未上传简历" />
        </template>
      </el-table>

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
    </el-card>

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
.mt { margin-top: 12px; }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-head h3 { margin: 0; font-size: 15px; color: #0f172a; display: flex; align-items: center; gap: 6px; }
.muted { color: #94a3b8; font-size: 12px; }
.up-icon { color: #94a3b8; }
.up-text { color: #1e293b; font-size: 14px; margin-top: 8px; }
.up-tip { color: #94a3b8; font-size: 12px; margin-top: 4px; }
.pager { display: flex; justify-content: flex-end; margin-top: 14px; }
.detail h4 { margin: 18px 0 8px; color: #0f172a; font-size: 14px; }
.detail .tags { display: flex; flex-wrap: wrap; gap: 6px; }
.detail .raw {
  background: #0f172a; color: #cbd5e1; padding: 12px; border-radius: 8px;
  font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
  max-height: 280px; overflow: auto;
}
.error-text { color: #dc2626; font-size: 12px; margin-left: 8px; }
:deep(.el-table__row) { cursor: pointer; }
</style>
