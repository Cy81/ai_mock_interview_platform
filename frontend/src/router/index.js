/**
 * 路由：全部懒加载 + meta.requiresAuth + meta.roles 控制。
 *
 *  - / 客户端工作台
 *  - /admin/* 管理后台（需要 admin/superadmin 角色）
 *  - 401 由拦截器处理；403 直接跳到 forbidden 页。
 */
import { createRouter, createWebHistory } from 'vue-router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'

import { useSessionStore } from '@/stores/session'


const clientRoutes = [
  {
    path: '/',
    name: 'client',
    component: () => import('@/layouts/ClientLayout.vue'),
    meta: { requiresAuth: true },
    redirect: { name: 'dashboard' },
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '面试记录' },
      },
      {
        path: 'resumes',
        name: 'resumes',
        component: () => import('@/views/ResumeUpload.vue'),
        meta: { title: '上传简历' },
      },
      {
        path: 'jobs',
        name: 'jobs',
        component: () => import('@/views/JobRecommend.vue'),
        meta: { title: '岗位匹配' },
      },
      {
        path: 'interviews',
        name: 'interviews',
        component: () => import('@/views/AIInterviewRoom.vue'),
        meta: { title: 'AI 面试房间', immersive: true },
      },
      {
        path: 'interviews/:id',
        name: 'interview-detail',
        component: () => import('@/views/AIInterviewRoom.vue'),
        meta: { title: 'AI 面试房间', immersive: true },
        props: true,
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('@/views/Reports.vue'),
        meta: { title: '评分报告' },
      },
      {
        path: 'reports/:id',
        name: 'report-detail',
        component: () => import('@/views/Reports.vue'),
        meta: { title: '评分报告' },
        props: true,
      },
    ],
  },
]

const adminRoutes = [
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, roles: ['admin', 'superadmin'] },
    redirect: { name: 'admin-dashboard' },
    children: [
      {
        path: '',
        name: 'admin-dashboard',
        component: () => import('@/views/admin/AdminDashboard.vue'),
        meta: { title: '后台总览' },
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/admin/AdminUsers.vue'),
        meta: { title: '用户管理' },
      },
      {
        path: 'jobs',
        name: 'admin-jobs',
        component: () => import('@/views/admin/AdminJobs.vue'),
        meta: { title: '岗位管理' },
      },
      {
        path: 'rag',
        name: 'admin-rag',
        redirect: { name: 'admin-questions' },
      },
      {
        path: 'questions',
        name: 'admin-questions',
        component: () => import('@/views/admin/AdminRag.vue'),
        meta: { title: '题库管理', ragType: 'question_bank' },
      },
      {
        path: 'documents',
        name: 'admin-documents',
        component: () => import('@/views/admin/AdminRag.vue'),
        meta: { title: '文档管理', ragType: 'knowledge_base' },
      },
      {
        path: 'ai-config',
        name: 'admin-ai-config',
        component: () => import('@/views/admin/AdminAiConfig.vue'),
        meta: { title: '模型配置' },
      },
      {
        path: 'ai-usage',
        name: 'admin-ai-usage',
        component: () => import('@/views/admin/AdminAiUsage.vue'),
        meta: { title: '用量观测' },
      },
      {
        path: 'ai-failures',
        name: 'admin-ai-failures',
        component: () => import('@/views/admin/AdminAiFailures.vue'),
        meta: { title: '异常监控' },
      },
      {
        path: 'interviews',
        name: 'admin-interviews',
        component: () => import('@/views/admin/AdminInterviews.vue'),
        meta: { title: '面试记录' },
      },
    ],
  },
]


const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
  },
  ...clientRoutes,
  ...adminRoutes,
  {
    path: '/forbidden',
    name: 'forbidden',
    component: () => import('@/views/Forbidden.vue'),
    meta: { public: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFound.vue'),
    meta: { public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

NProgress.configure({ showSpinner: false })

router.beforeEach((to) => {
  NProgress.start()
  const session = useSessionStore()
  if (to.meta.public) return true
  if (to.meta.requiresAuth && !session.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  const requiredRoles = to.meta.roles
  if (requiredRoles && !requiredRoles.includes(session.user?.role)) {
    return { name: 'forbidden' }
  }
  return true
})

router.afterEach((to) => {
  NProgress.done()
  document.title = to.meta.title
    ? `${to.meta.title} · AI 模拟面试`
    : 'AI 模拟面试系统'
})

export default router
