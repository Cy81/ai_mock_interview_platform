# User Client Productization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the user client into a candidate-facing product surface with top navigation, interview records, resume-based start flow, and chat-style interview room.

**Architecture:** Keep the existing FastAPI contracts unchanged for this phase. Update Vue components in place, preserving route names and API modules so existing backend tests remain valid.

**Tech Stack:** Vue 3, Vue Router, Pinia, Element Plus, lucide-vue-next, Vite.

---

## File Structure

- Modify `frontend/src/layouts/ClientLayout.vue`: replace admin-like sidebar with top product navigation.
- Modify `frontend/src/views/Dashboard.vue`: make the home page an interview-record hub with resume selection and quick workflow actions.
- Modify `frontend/src/views/MockInterview.vue`: reshape the interview room into a conversational layout while preserving current answer and SSE behavior.
- Add `frontend/tests/client-ui-structure.test.mjs`: Node structural tests that lock in the user/admin separation and chat-first UI markers.

## Tasks

### Task 1: Lock User UI Requirements With a Failing Test

- [ ] Add `frontend/tests/client-ui-structure.test.mjs` with assertions for:
  - client layout uses `.client-topnav`
  - client layout no longer uses `<el-aside`
  - dashboard exposes `.interview-records`
  - dashboard exposes `.resume-start-panel`
  - mock interview exposes `.chat-room`
  - mock interview exposes `.answer-composer`
- [ ] Run `node --test tests/client-ui-structure.test.mjs` from `frontend`.
- [ ] Expected result before implementation: FAIL because these markers do not exist.

### Task 2: Replace Client Sidebar With Top Product Navigation

- [ ] Modify `frontend/src/layouts/ClientLayout.vue`.
- [ ] Preserve logout and admin jump behavior.
- [ ] Add route-aware top nav links for 面试记录, 上传简历, 岗位匹配, AI 面试, and 评分报告.
- [ ] Use a candidate-facing light layout with constrained content width.
- [ ] Run `node --test tests/client-ui-structure.test.mjs`; expected remaining failures are dashboard and mock interview markers.

### Task 3: Rebuild Home Around Interview Records

- [ ] Modify `frontend/src/views/Dashboard.vue`.
- [ ] Keep loading `resumes`, `interviews`, and `jobs`.
- [ ] Add a resume selection panel that can start an interview by pushing `/interviews?resume_id=<id>&job_code=<code>`.
- [ ] Add interview records as the main section with status, date, score/report action, and continue action.
- [ ] Keep quick actions for upload resume and job matching.
- [ ] Run `node --test tests/client-ui-structure.test.mjs`; expected remaining failures are mock interview markers.

### Task 4: Make Interview Room Conversational

- [ ] Modify `frontend/src/views/MockInterview.vue`.
- [ ] Keep all existing create/answer/finish/SSE functions.
- [ ] Change presentation to chat messages: AI question, submitted candidate answer, AI feedback, and fixed composer.
- [ ] Keep history and new interview controls but make them secondary to the conversation.
- [ ] Run `node --test tests/client-ui-structure.test.mjs`; expected PASS.

### Task 5: Verify Build and Backend Baseline

- [ ] Run `npm run build` from `frontend`; expected PASS.
- [ ] Run `python -m pytest -q` from `backend`; expected existing 24 tests pass.
- [ ] Inspect `git diff --stat` and summarize scope.
