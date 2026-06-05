import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

function read(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
}

test('admin navigation exposes ai usage observability', () => {
  const layout = read('src/layouts/AdminLayout.vue')
  const router = read('src/router/index.js')
  const modules = read('src/api/modules.js')

  assert.match(layout, /用量观测/)
  assert.match(layout, /\/admin\/ai-usage/)
  assert.match(router, /admin-ai-usage/)
  assert.match(router, /AdminAiUsage\.vue/)
  assert.match(modules, /getAiUsageSummary/)
  assert.match(modules, /listAiUsage/)
})

test('admin ai usage page exposes summary cards and usage log table', () => {
  const source = read('src/views/admin/AdminAiUsage.vue')

  assert.match(source, /ai-usage-admin/)
  assert.match(source, /usage-summary-grid/)
  assert.match(source, /model-usage-table/)
  assert.match(source, /usage-log-table/)
  assert.match(source, /getAiUsageSummary/)
  assert.match(source, /listAiUsage/)
})
