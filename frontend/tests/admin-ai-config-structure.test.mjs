import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

function read(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
}

test('admin navigation exposes ai model configuration', () => {
  const layout = read('src/layouts/AdminLayout.vue')
  const router = read('src/router/index.js')
  const modules = read('src/api/modules.js')

  assert.match(layout, /模型配置/)
  assert.match(layout, /\/admin\/ai-config/)
  assert.match(router, /admin-ai-config/)
  assert.match(router, /AdminAiConfig\.vue/)
  assert.match(modules, /getAiConfig/)
  assert.match(modules, /updateAiConfig/)
  assert.match(modules, /testAiConfig/)
})

test('frontend dev script avoids vite temp config writes on Windows', () => {
  const packageJson = JSON.parse(read('package.json'))

  assert.match(packageJson.scripts.dev, /--configLoader runner/)
})

test('admin ai config page exposes model form and connection test surfaces', () => {
  const source = read('src/views/admin/AdminAiConfig.vue')

  assert.match(source, /ai-config-admin/)
  assert.match(source, /model-connection-test/)
  assert.match(source, /secret-field/)
  assert.match(source, /api_key/)
  assert.match(source, /base_url/)
  assert.match(source, /testAiConfig/)
})

test('admin ai config page exposes wire api selection for compatible gateways', () => {
  const source = read('src/views/admin/AdminAiConfig.vue')

  assert.match(source, /wire_api/)
  assert.match(source, /chat_completions/)
  assert.match(source, /responses/)
  assert.match(source, /请求协议|Wire API/)
})
