<script setup>
/**
 * 管理后台：用户管理——分页列表 + 启用/禁用切换。
 */
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshCw } from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)

async function load(p = page.value) {
  loading.value = true
  try {
    const resp = await adminApi.listUsers({ page: p, page_size: pageSize.value })
    list.value = resp.items || []
    total.value = resp.total || 0
    page.value = resp.page || p
  } catch (err) {
    ElMessage.error(err?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function toggle(row) {
  const action = row.is_active ? '禁用' : '启用'
  await ElMessageBox.confirm(`确认${action}用户 ${row.email}？`, `${action}用户`, {
    confirmButtonText: action,
    cancelButtonText: '取消',
    type: 'warning',
  })
  try {
    await adminApi.toggleUser(row.id, !row.is_active)
    ElMessage.success(`已${action}`)
    await load(page.value)
  } catch (err) {
    ElMessage.error(err?.message || '操作失败')
  }
}

onMounted(() => load(1))
</script>

<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <h3>用户列表</h3>
          <el-button text :icon="RefreshCw" :loading="loading" @click="load(page)">刷新</el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="list" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip />
        <el-table-column prop="full_name" label="姓名" width="120" />
        <el-table-column prop="role" label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="row.role === 'superadmin' ? 'danger' : row.role === 'admin' ? 'warning' : 'info'" size="small">
              {{ row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="180">
          <template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              :type="row.is_active ? 'danger' : 'success'"
              size="small"
              text
              @click="toggle(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
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
.pager { display: flex; justify-content: flex-end; margin-top: 14px; }
</style>
