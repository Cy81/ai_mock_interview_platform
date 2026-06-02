/**
 * 应用入口：注册 Element Plus、Pinia + 持久化、ECharts、全局错误处理。
 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPersist from 'pinia-plugin-persistedstate'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { use as echartsUse } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart, BarChart, PieChart, LineChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
} from 'echarts/components'

import App from './App.vue'
import router from './router'
import './assets/styles.css'

echartsUse([
  CanvasRenderer,
  RadarChart,
  BarChart,
  PieChart,
  LineChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent,
])

const app = createApp(App)
const pinia = createPinia()
pinia.use(piniaPersist)

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.config.errorHandler = (err, _, info) => {
  console.error('[Vue Error]', err, info)
}

window.addEventListener('unhandledrejection', (e) => {
  console.error('[UnhandledRejection]', e.reason)
})

app.mount('#app')

const loader = document.getElementById('app-loader')
if (loader) loader.remove()
