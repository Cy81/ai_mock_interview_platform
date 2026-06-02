<script setup>
/**
 * 管理后台：岗位管理——CRUD + 启用/禁用。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, RefreshCw } from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const list = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)
const submitting = ref(false)

const form = reactive({
  code: '',
  title: '',
  description: '',
  required_skills: '',
  nice_to_have_skills: '',
  seniority: 'junior-mid',
  salary_range: '',
  sort_order: 0,
})

function resetForm() {
  Object.assign(form, {
    code: '', title: '', description: '',
    required_skills: '', nice_to_have_skills: '',
    seniority: 'junior-mid', salary_range: '', sort_order: 0,
  })
}

async function load() {
  loading.value = true
  try {
    list.value = await adminApi.listJobs()
  } catch (err) {
    ElMessage.error(err?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    code: row.code,
    title: row.title,
    description: row.description,
    required_skills: (row.required_skills || []).join(', '),
    nice_to_have_skills: (row.nice_to_have_skills || []).join(', '),
    seniority: row.seniority || 'junior-mid',
    salary_range: row.salary_range || '',
    sort_order: row.sort_order || 0,
  })
  dialogVisible.value = true
}

function parseSkills(str) {
  return str.split(/[,，、]/).map((s) => s.trim()).filter(Boolean)
}

async function submit() {
  if (!form.title || !form.description) {
    ElMessage.warning('标题和描述必填')
    return
  }
  submitting.value = true
  const payload = {
    ...form,
    required_skills: parseSkills(form.required_skills),
    nice_to_have_skills: parseSkills(form.nice_to_have_skills),
  }
  try {
    if (editing.value) {
      await adminApi.updateJob(editing.value.id, payload)
      ElMessage.success('已更新')
    } else {
      if (!form.code) { ElMessage.warning('code 必填'); submitting.value = false; return }
      await adminApi.createJob(payload)
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    await load()
  } catch (err) {
    ElMessage.error(err?.message || '操作失败')
  } finally {
    submitting.value = false
  }
}

async function toggle(row) {
  try {
    await adminApi.toggleJob(row.id, !row.is_active)
    ElMessage.success(row.is_active ? '已下线' : '已上线')
    await load()
  } catch (err) {
    ElMessage.error(err?.message || '操作失败')
  }
}

async function remove(row) {
  await ElMessageBox.confirm(`删除岗位 ${row.title}？`, '删除', { type: 'warning' })
  try {
    await adminApi.deleteJob(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (err) {
    ElMessage.error(err?.message || '删除失败')
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <h3>岗位管理</h3>
          <div>
            <el-button type="primary" :icon="Plus" @click="openCreate">新增岗位</el-button>
            <el-button text :icon="RefreshCw" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="list" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="code" label="Code" width="160" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="160" />
        <el-table-column prop="seniority" label="级别" width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '上线' : '下线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sort_order" label="排序" width="70" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button text :type="row.is_active ? 'warning' : 'success'" size="small" @click="toggle(row)">
              {{ row.is_active ? '下线' : '上线' }}
            </el-button>
            <el-button text type="danger" size="small" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑岗位' : '新增岗位'" width="560px">
      <el-form label-position="top">
        <el-form-item v-if="!editing" label="Code（唯一标识）">
          <el-input v-model="form.code" placeholder="如 ai_app_engineer" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="必备技能（逗号分隔）">
              <el-input v-model="form.required_skills" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="加分技能（逗号分隔）">
              <el-input v-model="form.nice_to_have_skills" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="级别">
              <el-input v-model="form.seniority" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="薪资范围">
              <el-input v-model="form.salary_range" placeholder="如 20-40K" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="排序">
              <el-input-number v-model="form.sort_order" :min="0" :max="999" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-head h3 { margin: 0; font-size: 15px; color: #0f172a; }
</style>
