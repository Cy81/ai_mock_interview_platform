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

test('mock interview is driven by conversational AI turns instead of manual question submission', () => {
  const source = read('src/views/MockInterview.vue')

  assert.match(source, /conversation-flow/)
  assert.match(source, /conversationTurns/)
  assert.match(source, /v-for="turn in conversationTurns"/)
  assert.match(source, /sendAnswer/)
  assert.match(source, /advanceToNextQuestion/)
  assert.match(source, /submitting\.value\s*\|\|[\s\S]*awaitingInterviewer\.value/)
  assert.match(source, /回复 AI 面试官/)
  assert.match(source, /开始 AI 面试/)
  assert.match(source, /发送给面试官/)
  assert.match(source, /AI 面试官正在思考/)
  assert.match(source, /对话已完成，可以生成评分报告/)
  assert.match(source, /AI 面试官 · 第/)
  assert.doesNotMatch(source, /conversationQuestions/)
  assert.doesNotMatch(source, />\s*当前回答\s*</)
  assert.doesNotMatch(source, />\s*题量\s*</)
  assert.doesNotMatch(source, />\s*生成题目并开始\s*</)
  assert.doesNotMatch(source, />\s*提交回答\s*</)
  assert.doesNotMatch(source, />\s*上一题\s*</)
  assert.doesNotMatch(source, />\s*下一题\s*</)
})
