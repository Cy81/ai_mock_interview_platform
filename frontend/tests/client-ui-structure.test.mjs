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
  assert.match(source, /to: '\/resumes'/)
  assert.match(source, /to: '\/jobs'/)
  assert.match(source, /to: '\/interviews'/)
})

test('client shell exposes production connectivity and support affordances', () => {
  const source = read('src/layouts/ClientLayout.vue')

  assert.match(source, /quiet-status-pill/)
  assert.match(source, /checkSystemStatus/)
  assert.match(source, /navigator\.onLine/)
  assert.match(source, /support-drawer/)
  assert.match(source, /serviceStatus/)
  assert.match(source, /supportVisible/)
  assert.doesNotMatch(source, /<section class="system-status-bar"/)
})

test('dashboard feels like an interview launch cockpit instead of a records table', () => {
  const source = read('src/views/Dashboard.vue')

  assert.match(source, /candidate-journey/)
  assert.match(source, /primary-start-card/)
  assert.match(source, /准备一场真实 AI 面试/)
  assert.match(source, /interview-records/)
  assert.match(source, /resume-start-panel/)
  assert.match(source, /startInterview/)
  assert.match(source, /selectedResumeId/)
})

test('dashboard guides candidates with a readiness checklist', () => {
  const source = read('src/views/Dashboard.vue')

  assert.match(source, /readiness-checklist/)
  assert.match(source, /readinessItems/)
  assert.match(source, /readinessScore/)
  assert.match(source, /readiness-score/)
  assert.match(source, /before-interview-panel/)
})

test('resume upload is a candidate resume workspace, not an admin table', () => {
  const source = read('src/views/ResumeUpload.vue')

  assert.match(source, /resume-command-center/)
  assert.match(source, /upload-dropzone-panel/)
  assert.match(source, /resume-timeline/)
  assert.match(source, /parsed-resume-grid/)
  assert.doesNotMatch(source, /<el-table\b/)
})

test('job matching is a guided recommendation studio with clear next action', () => {
  const source = read('src/views/JobRecommend.vue')

  assert.match(source, /job-match-studio/)
  assert.match(source, /match-command-panel/)
  assert.match(source, /recommendation-board/)
  assert.match(source, /job-match-card/)
  assert.match(source, /startInterview/)
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
  assert.doesNotMatch(source, /conversationQuestions/)
})

test('mock interview gives production-grade guidance while answering', () => {
  const source = read('src/views/MockInterview.vue')

  assert.match(source, /question-rail/)
  assert.match(source, /composerDisabledReason/)
  assert.match(source, /autosaveState/)
  assert.match(source, /interview-quality-panel/)
  assert.match(source, /responseQualityHints/)
  assert.match(source, /qualityChecklist/)
}
)

test('interview routes use a dedicated resume-aware AI interview room', () => {
  const router = read('src/router/index.js')
  const room = read('src/views/AIInterviewRoom.vue')

  assert.match(router, /AIInterviewRoom\.vue/)
  assert.match(room, /ai-interview-room/)
  assert.match(room, /resume-insight-panel/)
  assert.match(room, /interview-transcript/)
  assert.match(room, /candidate-composer/)
  assert.match(room, /focus-interview-layout/)
  assert.match(room, /context-ribbon/)
  assert.match(room, /followupStrategy/)
  assert.match(room, /loadResumeProfile/)
  assert.match(room, /profileSignals/)
  assert.match(room, /conversational:\s*true/)
  assert.match(room, /interviewApi\.turn/)
  assert.doesNotMatch(room, /interviewApi\.answer\(current\.value\.id/)
})
