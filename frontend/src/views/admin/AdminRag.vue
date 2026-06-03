<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  BookOpenCheck,
  CheckCircle2,
  FileStack,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Upload,
} from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const route = useRoute()

const list = ref([])
const chunks = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const dialogVisible = ref(false)
const batchVisible = ref(false)
const testVisible = ref(false)
const chunkVisible = ref(false)
const submitting = ref(false)
const batchSubmitting = ref(false)
const testLoading = ref(false)
const chunkLoading = ref(false)
const editing = ref(null)
const chunkDoc = ref(null)
const keyword = ref('')

const form = reactive({
  title: '',
  content: '',
})
const batch = reactive({
  text: '',
})
const testForm = reactive({
  query: '',
  top_k: 5,
})
const testHits = ref([])

const ragType = computed(() => route.meta.ragType || 'question_bank')
const isQuestionBank = computed(() => ragType.value === 'question_bank')
const modeClass = computed(() =>
  isQuestionBank.value ? 'question-bank-admin' : 'knowledge-document-admin',
)
const mode = computed(() =>
  isQuestionBank.value
    ? {
        icon: BookOpenCheck,
        title: '题库管理',
        subtitle: '批量导入面试题，完成向量索引，并用检索测试校验题库质量。',
        createLabel: '新增题目',
        searchPlaceholder: '搜索题目 / 分类 / 岗位...',
      }
    : {
        icon: FileStack,
        title: '文档管理',
        subtitle: '上传知识文档，跟踪向量化状态，并查看每篇文档的分块明细。',
        createLabel: '新增文档',
        searchPlaceholder: '搜索文档标题...',
      },
)

const readyCount = computed(
  () => list.value.filter((item) => ['ready', 'indexed'].includes(item.index_status)).length,
)
const failedCount = computed(
  () => list.value.filter((item) => item.index_status === 'failed').length,
)
const chunkTotal = computed(() =>
  list.value.reduce((sum, item) => sum + Number(item.chunk_count || 0), 0),
)
const tokenTotal = computed(() =>
  list.value.reduce((sum, item) => sum + Number(item.total_tokens || 0), 0),
)

const statusMeta = {
  pending: { type: 'info', label: '待索引' },
  indexing: { type: 'warning', label: '索引中' },
  ready: { type: 'success', label: '已向量化' },
  indexed: { type: 'success', label: '已向量化' },
  failed: { type: 'danger', label: '失败' },
}

function indexStatus(row) {
  return statusMeta[row.index_status] || { type: 'info', label: row.index_status || '-' }
}

function resetForms() {
  editing.value = null
  Object.assign(form, { title: '', content: '' })
  Object.assign(testForm, { query: '', top_k: 5 })
  testHits.value = []
  chunks.value = []
  chunkDoc.value = null
}

async function load(p = page.value) {
  loading.value = true
  try {
    const resp = await adminApi.listRagDocs({
      rag_type: ragType.value,
      keyword: keyword.value || undefined,
      page: p,
      page_size: pageSize.value,
    })
    list.value = resp.items || resp || []
    total.value = resp.total || list.value.length
    page.value = resp.page || p
  } catch (err) {
    ElMessage.error(err?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, { title: '', content: '' })
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, { title: row.title, content: '' })
  dialogVisible.value = true
}

async function submit() {
  if (!form.title.trim()) {
    ElMessage.warning('标题必填')
    return
  }
  if (!editing.value && !form.content.trim()) {
    ElMessage.warning(isQuestionBank.value ? '题目内容必填' : '文档内容必填')
    return
  }
  submitting.value = true
  try {
    if (editing.value) {
      await adminApi.updateRagDoc(editing.value.id, {
        title: form.title,
      })
      ElMessage.success('已更新标题')
    } else {
      await adminApi.createRagDoc({
        rag_type: ragType.value,
        title: form.title,
        content: form.content,
        metadata: { source: 'admin-manual' },
      })
      ElMessage.success('已创建并完成索引')
    }
    dialogVisible.value = false
    await load(page.value)
  } catch (err) {
    ElMessage.error(err?.message || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function submitBatchImport() {
  const lines = batch.text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
  if (!lines.length) {
    ElMessage.warning('请输入题目，每行一题')
    return
  }
  batchSubmitting.value = true
  try {
    await Promise.all(
      lines.map((line, index) =>
        adminApi.createRagDoc({
          rag_type: 'question_bank',
          title: line.slice(0, 80) || `批量题目 ${index + 1}`,
          content: line,
          metadata: { source: 'batch-import' },
        }),
      ),
    )
    ElMessage.success(`已导入 ${lines.length} 道题`)
    batch.text = ''
    batchVisible.value = false
    await load(1)
  } catch (err) {
    ElMessage.error(err?.message || '批量导入失败')
  } finally {
    batchSubmitting.value = false
  }
}

async function uploadFile(options) {
  const data = new FormData()
  data.append('rag_type', ragType.value)
  data.append('title', options.file.name)
  data.append('file', options.file)
  try {
    await adminApi.uploadRagDoc(data)
    ElMessage.success('上传成功，后台正在索引')
    await load(1)
  } catch (err) {
    ElMessage.error(err?.message || '上传失败')
  }
}

async function reindex(row) {
  try {
    await adminApi.reindexRagDoc(row.id)
    ElMessage.success('已提交重索引任务')
    await load(page.value)
  } catch (err) {
    ElMessage.error(err?.message || '重索引失败')
  }
}

async function toggleDoc(row) {
  try {
    await adminApi.toggleRagDoc(row.id, !row.is_active)
    ElMessage.success(row.is_active ? '已禁用' : '已启用')
    await load(page.value)
  } catch (err) {
    ElMessage.error(err?.message || '操作失败')
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`删除 "${row.title}"？`, '删除确认', { type: 'warning' })
  try {
    await adminApi.deleteRagDoc(row.id)
    ElMessage.success('已删除')
    await load(page.value)
  } catch (err) {
    ElMessage.error(err?.message || '删除失败')
  }
}

function openRetrieveTest() {
  testHits.value = []
  testVisible.value = true
}

async function testRetrieve() {
  if (!testForm.query.trim()) {
    ElMessage.warning('请输入查询')
    return
  }
  testLoading.value = true
  try {
    const resp = await adminApi.testRetrieve({
      rag_type: ragType.value,
      query: testForm.query,
      top_k: testForm.top_k,
    })
    testHits.value = resp.hits || resp || []
  } catch (err) {
    ElMessage.error(err?.message || '检索失败')
  } finally {
    testLoading.value = false
  }
}

async function loadChunks(row) {
  chunkDoc.value = row
  chunkVisible.value = true
  chunkLoading.value = true
  chunks.value = []
  try {
    const resp = await adminApi.listRagChunks(row.id, { page: 1, page_size: 100 })
    chunks.value = resp.items || resp || []
  } catch (err) {
    ElMessage.error(err?.message || '加载分块失败')
  } finally {
    chunkLoading.value = false
  }
}

watch(ragType, async () => {
  resetForms()
  await load(1)
})

onMounted(() => load(1))
</script>

<template>
  <div class="rag-admin" :class="modeClass">
    <section class="admin-hero">
      <div>
        <p>KNOWLEDGE RAG</p>
        <h2><component :is="mode.icon" :size="22" /> {{ mode.title }}</h2>
        <span>{{ mode.subtitle }}</span>
      </div>
      <div class="hero-actions">
        <el-button
          v-if="isQuestionBank"
          class="batch-import"
          :icon="Upload"
          @click="batchVisible = true"
        >
          批量导入
        </el-button>
        <el-upload
          v-else
          :show-file-list="false"
          :http-request="uploadFile"
          accept=".txt,.md,.pdf,.docx"
        >
          <el-button :icon="Upload">上传文档</el-button>
        </el-upload>
        <el-button type="primary" :icon="Plus" @click="openCreate">
          {{ mode.createLabel }}
        </el-button>
        <el-button :icon="Search" @click="openRetrieveTest">检索测试</el-button>
        <el-button text :icon="RefreshCw" :loading="loading" @click="load(page)" />
      </div>
    </section>

    <section class="stat-grid">
      <div class="stat-card">
        <strong>{{ total }}</strong>
        <span>{{ isQuestionBank ? '题目总数' : '文档总数' }}</span>
      </div>
      <div class="stat-card">
        <strong>{{ readyCount }}</strong>
        <span>已向量化</span>
      </div>
      <div class="stat-card">
        <strong>{{ chunkTotal }}</strong>
        <span>分块总数</span>
      </div>
      <div class="stat-card">
        <strong>{{ failedCount }}</strong>
        <span>异常数量</span>
      </div>
    </section>

    <section class="table-panel">
      <div class="filter-row">
        <el-input
          v-model="keyword"
          :placeholder="mode.searchPlaceholder"
          clearable
          style="max-width: 320px"
          @keyup.enter="load(1)"
          @clear="load(1)"
        />
        <el-button :icon="Search" @click="load(1)">搜索</el-button>
        <span class="muted">Token 粗估 {{ tokenTotal }}</span>
      </div>

      <el-table v-loading="loading" :data="list" stripe>
        <el-table-column prop="id" label="ID" width="68" />
        <el-table-column prop="title" :label="isQuestionBank ? '题目 / 答案' : '文档标题'" min-width="260" show-overflow-tooltip />
        <el-table-column label="向量化" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="indexStatus(row).type">
              {{ indexStatus(row).label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="分块" width="90" />
        <el-table-column prop="total_tokens" label="Tokens" width="100" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.last_error || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="310" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="loadChunks(row)">
              分块
            </el-button>
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button text type="warning" size="small" @click="reindex(row)">重建索引</el-button>
            <el-button text :type="row.is_active ? 'info' : 'success'" size="small" @click="toggleDoc(row)">
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button text type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
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
    </section>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑标题' : mode.createLabel" width="620px">
      <el-form label-position="top">
        <el-form-item :label="isQuestionBank ? '题目标题' : '文档标题'">
          <el-input v-model="form.title" maxlength="200" />
        </el-form-item>
        <el-form-item v-if="!editing" :label="isQuestionBank ? '题目内容 / 参考答案' : '文档内容'">
          <el-input v-model="form.content" type="textarea" :rows="10" maxlength="200000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="batchVisible" title="批量导入题目" width="680px">
      <div class="batch-import-panel">
        <p class="muted">每行一题，保存后会逐条写入题库并立即向量化。</p>
        <el-input
          v-model="batch.text"
          type="textarea"
          :rows="12"
          placeholder="示例：请解释 FastAPI 依赖注入的执行顺序，并说明如何做权限校验。"
          maxlength="200000"
        />
      </div>
      <template #footer>
        <el-button @click="batchVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchSubmitting" @click="submitBatchImport">
          导入并向量化
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testVisible" :title="`${mode.title}检索测试`" width="720px">
      <el-form :inline="true" label-position="top">
        <el-form-item label="查询">
          <el-input v-model="testForm.query" style="width: 360px" placeholder="输入岗位、技能或问题描述" />
        </el-form-item>
        <el-form-item label="Top K">
          <el-input-number v-model="testForm.top_k" :min="1" :max="20" />
        </el-form-item>
        <el-form-item label=" ">
          <el-button type="primary" :loading="testLoading" @click="testRetrieve">检索</el-button>
        </el-form-item>
      </el-form>
      <el-divider />
      <el-empty v-if="!testHits.length" description="暂无结果" :image-size="60" />
      <div v-else class="hits">
        <article v-for="hit in testHits" :key="hit.chunk_id" class="hit-item">
          <div class="hit-head">
            <strong>{{ hit.title }}</strong>
            <el-tag size="small">{{ hit.score?.toFixed?.(4) }}</el-tag>
          </div>
          <p>{{ (hit.content || '').slice(0, 420) }}</p>
        </article>
      </div>
    </el-dialog>

    <el-drawer
      v-model="chunkVisible"
      class="chunk-drawer"
      :title="chunkDoc ? `分块详情：${chunkDoc.title}` : '分块详情'"
      direction="rtl"
      size="640px"
    >
      <el-skeleton v-if="chunkLoading" :rows="6" animated />
      <el-empty v-else-if="!chunks.length" description="暂无分块" />
      <div v-else class="chunk-list">
        <article v-for="chunk in chunks" :key="chunk.id" class="chunk-item">
          <div class="chunk-head">
            <strong>#{{ chunk.chunk_index }}</strong>
            <span>
              <Layers :size="13" /> {{ chunk.token_count }} tokens
            </span>
            <el-tag size="small" :type="chunk.is_active ? 'success' : 'info'">
              {{ chunk.is_active ? '启用' : '禁用' }}
            </el-tag>
          </div>
          <p>{{ chunk.content }}</p>
          <small v-if="chunk.extra_meta?.title">
            <CheckCircle2 :size="12" /> {{ chunk.extra_meta.title }}
          </small>
        </article>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.rag-admin {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.admin-hero,
.table-panel,
.stat-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.admin-hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
}

.admin-hero p {
  margin: 0 0 4px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.admin-hero h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: #0f172a;
  font-size: 22px;
}

.admin-hero span {
  display: block;
  margin-top: 6px;
  color: #64748b;
  font-size: 13px;
}

.hero-actions,
.filter-row,
.hit-head,
.chunk-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hero-actions {
  justify-content: flex-end;
  flex-wrap: wrap;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  min-height: 92px;
  padding: 16px 18px;
}

.stat-card strong {
  display: block;
  color: #3344ee;
  font-size: 28px;
}

.knowledge-document-admin .stat-card strong {
  color: #0f766e;
}

.stat-card span {
  color: #64748b;
  font-size: 13px;
}

.table-panel {
  padding: 16px;
}

.filter-row {
  justify-content: space-between;
  margin-bottom: 14px;
}

.muted {
  color: #94a3b8;
  font-size: 12px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.batch-import-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hits {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hit-item,
.chunk-item {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.hit-head {
  justify-content: space-between;
}

.hit-head strong {
  color: #0f172a;
  font-size: 13px;
}

.hit-item p,
.chunk-item p {
  margin: 8px 0 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chunk-head {
  justify-content: flex-start;
}

.chunk-head strong {
  color: #0f172a;
}

.chunk-head span,
.chunk-item small {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #64748b;
  font-size: 12px;
}

.chunk-item small {
  margin-top: 8px;
}

@media (max-width: 980px) {
  .admin-hero,
  .filter-row {
    align-items: stretch;
    flex-direction: column;
  }

  .hero-actions {
    justify-content: flex-start;
  }

  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
