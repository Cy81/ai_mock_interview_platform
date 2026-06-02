<script setup>
/**
 * 管理后台总览：用户/面试/RAG 三组统计卡 + 最近面试列表。
 */
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Activity, Database, Users } from 'lucide-vue-next'
import { adminApi } from '@/api/modules'

const loading = ref(false)
const userStats = ref(null)
const interviewStats = ref(null)
const ragStats = ref(null)

async function load() {
  loading.value = true
  try {
    const [u, i, r] = await Promise.all([
      adminApi.userStats(),
      adminApi.interviewStats(),
      adminApi.ragStats(),
    ])
    userStats.value = u
    interviewStats.value = i
    ragStats.value = r
  } catch (err) {
    ElMessage.error(err?.message || '加载统计失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="admin-dash">
    <el-skeleton v-if="loading" :rows="6" animated />
    <template v-else>
      <el-row :gutter="16">
        <el-col :xs="24" :md="8">
          <el-card shadow="hover" class="stat-card blue">
            <Users :size="28" />
            <div>
              <strong>{{ userStats?.total_users ?? '—' }}</strong>
              <span>注册用户</span>
            </div>
            <small>活跃 {{ userStats?.active_users ?? 0 }} · 管理员 {{ userStats?.admin_count ?? 0 }}</small>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-card shadow="hover" class="stat-card amber">
            <Activity :size="28" />
            <div>
              <strong>{{ interviewStats?.total ?? '—' }}</strong>
              <span>面试总数</span>
            </div>
            <small>已完成 {{ interviewStats?.completed ?? 0 }} · 进行中 {{ interviewStats?.in_progress ?? 0 }}</small>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-card shadow="hover" class="stat-card violet">
            <Database :size="28" />
            <div>
              <strong>{{ ragStats?.total_documents ?? '—' }}</strong>
              <span>RAG 文档</span>
            </div>
            <small>分块 {{ ragStats?.total_chunks ?? 0 }} · 已索引 {{ ragStats?.indexed_chunks ?? 0 }}</small>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="mt">
        <template #header>
          <div class="card-head"><h3>平台概况</h3></div>
        </template>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="平均分">
            {{ interviewStats?.avg_score?.toFixed?.(1) ?? '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="最高分">
            {{ interviewStats?.max_score ?? '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="题库文档">
            {{ ragStats?.question_bank_docs ?? 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="知识库文档">
            {{ ragStats?.knowledge_base_docs ?? 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="锁定用户">
            {{ userStats?.locked_users ?? 0 }}
          </el-descriptions-item>
          <el-descriptions-item label="今日新增面试">
            {{ interviewStats?.today_count ?? 0 }}
          </el-descriptions-item>
        </el-descriptions>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.admin-dash { display: flex; flex-direction: column; gap: 16px; }
.mt { margin-top: 4px; }
.stat-card {
  display: flex; align-items: center; gap: 14px; padding: 6px 0;
  border-radius: 14px; color: #fff; position: relative; overflow: hidden;
}
.stat-card :deep(.el-card__body) { display: flex; align-items: center; gap: 14px; width: 100%; flex-wrap: wrap; }
.stat-card strong { font-size: 28px; display: block; }
.stat-card span { font-size: 12px; opacity: .9; }
.stat-card small { width: 100%; font-size: 11px; opacity: .8; }
.stat-card.blue { background: linear-gradient(135deg,#0ea5e9,#3b82f6); }
.stat-card.amber { background: linear-gradient(135deg,#f59e0b,#f97316); }
.stat-card.violet { background: linear-gradient(135deg,#8b5cf6,#6366f1); }
.card-head { display: flex; justify-content: space-between; align-items: center; }
.card-head h3 { margin: 0; font-size: 15px; color: #0f172a; }
</style>
