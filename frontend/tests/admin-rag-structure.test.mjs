import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

function read(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
}

test('admin navigation separates question bank and knowledge documents', () => {
  const layout = read('src/layouts/AdminLayout.vue')
  const router = read('src/router/index.js')

  assert.match(layout, /题库管理/)
  assert.match(layout, /文档管理/)
  assert.match(layout, /\/admin\/questions/)
  assert.match(layout, /\/admin\/documents/)
  assert.match(router, /admin-questions/)
  assert.match(router, /admin-documents/)
})

test('admin rag page exposes batch import, retrieval test, and chunk drawer surfaces', () => {
  const source = read('src/views/admin/AdminRag.vue')

  assert.match(source, /question-bank-admin/)
  assert.match(source, /knowledge-document-admin/)
  assert.match(source, /batch-import/)
  assert.match(source, /chunk-drawer/)
  assert.match(source, /loadChunks/)
  assert.match(source, /listRagChunks/)
})
