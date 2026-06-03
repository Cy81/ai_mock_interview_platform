import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import assert from 'node:assert/strict'

function read(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
}

test('client layout is a candidate product shell instead of an admin sidebar', () => {
  const source = read('src/layouts/ClientLayout.vue')

  assert.match(source, /client-topnav/)
  assert.doesNotMatch(source, /<el-aside\b/)
  assert.match(source, /面试记录/)
  assert.match(source, /上传简历/)
  assert.match(source, /岗位匹配/)
})

test('dashboard centers the user workflow on interview records and resume start', () => {
  const source = read('src/views/Dashboard.vue')

  assert.match(source, /interview-records/)
  assert.match(source, /resume-start-panel/)
  assert.match(source, /startInterview/)
  assert.match(source, /选择简历/)
})

test('mock interview uses a chat room and persistent answer composer', () => {
  const source = read('src/views/MockInterview.vue')

  assert.match(source, /chat-room/)
  assert.match(source, /answer-composer/)
  assert.match(source, /interviewer-message/)
  assert.match(source, /candidate-message/)
})
