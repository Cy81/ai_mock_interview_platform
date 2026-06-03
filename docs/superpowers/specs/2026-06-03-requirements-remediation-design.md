# Requirements Remediation Design

**Goal:** Align the platform with `D:\编程\python学习\实战项目\需求.md`, using the requirement file as the source of truth.

**Scope:** This remediation is split into three independently testable phases so the project stays runnable after each merge.

## Requirement Baseline

- User client and admin backoffice must be separated visually and functionally.
- The user client should look like a candidate-facing product, not a management system.
- The user client must include interview records, resume upload and persistence, resume analysis, job matching, and a conversational AI mock interview flow.
- The admin backoffice must include question bank management, batch question import, vector indexing, retrieval testing, knowledge document management, document vectorization, and chunk/index status visibility.
- AI engineering controls must include dynamic LLM configuration, model availability testing, LLM usage observability, and failure/exception monitoring.

## Architecture

The existing backend already has the main domain objects: resumes, jobs, interviews, reports, RAG documents, RAG chunks, LangChain interview agents, and SSE streaming. The remediation keeps those APIs stable where possible and reshapes the frontend into two clearer product surfaces:

- `/` user client: top navigation, candidate workflow, product-like cards, interview records as the main home view, and a chat-first interview room.
- `/admin` backoffice: dense operational UI with separate admin entries for question bank, knowledge documents, retrieval tests, model configuration, usage, and failures.

Backend additions will be incremental. RAG already stores document chunk counts and index status, so the first admin work can be mostly route/view separation. Chunk detail and AI observability require new read endpoints and persistence tables.

## Phase 1: User Client Productization

This phase changes the user-facing experience without changing backend contracts.

- Replace the client sidebar shell with a top navigation shell.
- Make the home page center on interview records and starting a new interview from a selected parsed resume.
- Keep resume upload and job matching reachable as first-class top nav items.
- Rework the mock interview page toward a chat-room layout: AI interviewer messages, candidate answer cards, progress, and fixed answer composer.
- Preserve existing APIs: `resumeApi.list`, `jobApi.list`, `interviewApi.list`, `interviewApi.create`, `interviewApi.answer`, and `interviewApi.stream`.

## Phase 2: Admin RAG Separation

This phase clarifies backoffice IA and admin workflows.

- Split the current `AdminRag.vue` surface into question bank and knowledge document modes or views.
- Question bank view: filters, batch import entry, vectorized status, retrieval test, and rebuild actions.
- Knowledge document view: document upload, vectorization status, chunk count, token count, last error, and chunk detail drawer.
- Add backend endpoint for listing chunks for a document: `GET /api/v1/admin/rag/documents/{id}/chunks`.

## Phase 3: AI Engineering Operations

This phase adds operational controls.

- Add dynamic LLM provider/model configuration in admin.
- Add an availability test endpoint that checks API URL/key/model configuration without saving invalid settings.
- Persist LLM request usage: provider, model, prompt tokens, completion tokens, latency, status, route, and error class.
- Add admin views for usage charts and failure/exception records.

## Testing Strategy

- Backend: pytest for new endpoints, schema behavior, and observability persistence.
- Frontend: add lightweight structural tests for user/admin separation, then build verification with `npm run build`.
- Browser smoke: start local backend and frontend, verify user home, resume upload navigation, job match navigation, interview record/start flow, and chat interview layout.

## Current Phase Decision

Implement Phase 1 first. It directly addresses the strongest complaint in `需求.md`: the user client currently feels like a management platform.
