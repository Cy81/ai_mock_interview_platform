<script setup>
/**
 * 管理后台：面试记录——分页列表 + 状态筛选。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { RefreshCw } from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const statusFilter = ref('')

const statusMeta = {
  created: { type: 'info', label: '已创建' },
  generating: { type: 'warning', label: '生成中' },
  in_progress: { type: 'primary', label: '进行中' },
  scoring: { type: 'warning', label: '评分中' },
  completed: { type: 'success', label: '已完成' },
  failed: { type: 'danger', label: '失败' },
  cancelled: { type: 'info', label: '已取消' },
}

async function load(p = page.value) {
  loading.value = true
  try {
    const params = { page: p, page_size: pageSize.value }
    if (statusFilter.value) params.status = statusFilter.value
    const resp = await adminApi.listInterviews(params)
    list.value = resp.items || resp || []
    total.value = resp.total || list.value.length
    page.value = resp.page || p
  } catch (err) {
    ElMessage.error(err?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  load(1)
}

onMounted(() => load(1))
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <h3>面试记录</h3>
          <div class="head-actions">
            <el-select
              v-model="statusFilter"
              placeholder="全部状态"
              clearable
              style="width: 140px"
              @change="onFilterChange"
            >
              <el-option
                v-for="(meta, key) in statusMeta"
                :key="key"
                :value="key"
                :label="meta.label"
              />
            </el-select>
            <el-button text :icon="RefreshCw" :loading="loading" @click="load(page)">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table v-loading="loading" :data="list" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="user_email" label="用户" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.user_email || row.user_id || '—' }}</template>
        </el-table-column>
        <el-table-column prop="job_title" label="岗位" width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusMeta[row.status]?.type || 'info'" size="small">
              {{ statusMeta[row.status]?.label || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="overall_score" label="总分" width="80">
          <template #default="{ row }">{{ row.overall_score ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="question_count" label="题数" width="70" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="完成时间" width="180">
          <template #default="{ row }">
            {{ row.completed_at ? new Date(row.completed_at).toLocaleString() : '—' }}
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
  </div>
</template>

<style scoped>
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-head h3 { margin: 0; font-size: 15px; color: #0f172a; }
.head-actions { display: flex; gap: 10px; align-items: center; }
.pager { display: flex; justify-content: flex-end; margin-top: 14px; }
</style>
