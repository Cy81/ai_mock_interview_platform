<script setup>
/**
 * 管理后台：RAG 知识库管理——文档 CRUD + 上传 + 重索引 + 测试检索。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Database, Plus, RefreshCw, Search, Upload } from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const dialogVisible = ref(false)
const testVisible = ref(false)
const submitting = ref(false)
const editing = ref(null)

const form = reactive({
  rag_type: 'question_bank',
  title: '',
  content: '',
})

const testForm = reactive({
  rag_type: 'question_bank',
  query: '',
  top_k: 5,
})
const testHits = ref([])
const testLoading = ref(false)

async function load(p = page.value) {
  loading.value = true
  try {
    const resp = await adminApi.listRagDocs({ page: p, page_size: pageSize.value })
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
  Object.assign(form, { rag_type: 'question_bank', title: '', content: '' })
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, { rag_type: row.rag_type, title: row.title, content: row.content || '' })
  dialogVisible.value = true
}

async function submit() {
  if (!form.title || !form.content) {
    ElMessage.warning('标题和内容必填')
    return
  }
  submitting.value = true
  try {
    if (editing.value) {
      await adminApi.updateRagDoc(editing.value.id, form)
      ElMessage.success('已更新')
    } else {
      await adminApi.createRagDoc(form)
      ElMessage.success('已创建，后台正在索引')
    }
    dialogVisible.value = false
    await load(page.value)
  } catch (err) {
    ElMessage.error(err?.message || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function uploadFile(options) {
  const data = new FormData()
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
  await ElMessageBox.confirm(`删除文档 "${row.title}"？`, '删除', { type: 'warning' })
  try {
    await adminApi.deleteRagDoc(row.id)
    ElMessage.success('已删除')
    await load(page.value)
  } catch (err) {
    ElMessage.error(err?.message || '删除失败')
  }
}

async function testRetrieve() {
  if (!testForm.query) { ElMessage.warning('请输入查询'); return }
  testLoading.value = true
  try {
    const resp = await adminApi.testRetrieve(testForm)
    testHits.value = resp.hits || resp || []
  } catch (err) {
    ElMessage.error(err?.message || '检索失败')
  } finally {
    testLoading.value = false
  }
}

onMounted(() => load(1))
</script>

<template>
  <div class="rag-admin">
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <h3><Database :size="16" /> RAG 文档管理</h3>
          <div class="head-actions">
            <el-upload :show-file-list="false" :http-request="uploadFile" accept=".txt,.md,.pdf,.docx">
              <el-button :icon="Upload">上传文件</el-button>
            </el-upload>
            <el-button type="primary" :icon="Plus" @click="openCreate">新增文档</el-button>
            <el-button :icon="Search" @click="testVisible = true">测试检索</el-button>
            <el-button text :icon="RefreshCw" :loading="loading" @click="load(page)" />
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="list" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="rag_type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.rag_type === 'question_bank' ? 'primary' : 'success'">
              {{ row.rag_type === 'question_bank' ? '题库' : '知识库' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="索引状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.index_status === 'indexed' ? 'success' : row.index_status === 'failed' ? 'danger' : 'warning'">
              {{ row.index_status || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button text type="warning" size="small" @click="reindex(row)">重索引</el-button>
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
    </el-card>

    <!-- 新增/编辑 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑文档' : '新增文档'" width="560px">
      <el-form label-position="top">
        <el-form-item label="RAG 类型">
          <el-radio-group v-model="form.rag_type">
            <el-radio value="question_bank">题库</el-radio>
            <el-radio value="knowledge_base">知识库</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="form.title" maxlength="200" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="8" maxlength="100000" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 测试检索 -->
    <el-dialog v-model="testVisible" title="测试检索" width="600px">
      <el-form :inline="true" label-position="top">
        <el-form-item label="RAG 类型">
          <el-radio-group v-model="testForm.rag_type">
            <el-radio value="question_bank">题库</el-radio>
            <el-radio value="knowledge_base">知识库</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="查询">
          <el-input v-model="testForm.query" style="width: 260px" />
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
        <div v-for="hit in testHits" :key="hit.id" class="hit-item">
          <div class="hit-head">
            <strong>{{ hit.title }}</strong>
            <el-tag size="small">{{ hit.score?.toFixed?.(4) }}</el-tag>
          </div>
          <p class="muted">{{ (hit.content || '').slice(0, 300) }}</p>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.rag-admin { display: flex; flex-direction: column; gap: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.card-head h3 { margin: 0; font-size: 15px; color: #0f172a; display: flex; align-items: center; gap: 6px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.pager { display: flex; justify-content: flex-end; margin-top: 14px; }
.muted { color: #94a3b8; font-size: 12px; }
.hits { display: flex; flex-direction: column; gap: 10px; }
.hit-item { padding: 10px; border: 1px solid #e2e8f0; border-radius: 8px; }
.hit-head { display: flex; justify-content: space-between; align-items: center; }
.hit-head strong { color: #0f172a; font-size: 13px; }
.hit-item p { margin: 4px 0 0; line-height: 1.6; }
</style>
