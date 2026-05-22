# Compliance Sandbox — Unified Roadmap

> Объединяет: оригинальный ROADMAP + Senior Code Review Report (файл) + Code Review сессии + анализ покрытия Vanta.
> Принцип: один атомарный Task.md → Джимми реализует → Claude проверяет.

---

## Текущее состояние (выполнено)

| # | Задача | Результат |
|---|--------|-----------|
| 1 | Evidence Tracker API (FastAPI + PostgreSQL + Docker) | ✅ |
| 2 | LocalStack + Sandbox Auditor (boto3, 9 AUTO-контролей) | ✅ |
| 3 | Okta интеграция (CC6.1, CC6.2, CC6.3) | ✅ |
| 4 | SOAR-оркестратор (pipeline runner) | ✅ |
| 5 | GitHub интеграция (CC8.1, CC3.4) | ✅ |
| 6 | Slack-бот (human-in-the-loop аппрувы) | ✅ |
| 7 | AI Policy Agent (OpenRouter + Gemini fallback) | ✅ |
| 8 | Prowler Runner (160 SOC 2 проверок по каталогу) | ✅ |
| 9 | EC2 Security Groups + DynamoDB Encryption | ✅ |
| 10 | HR Agent + Survey Agent (5 Okta-проверок, опрос персонала) | ✅ |
| 10b | GitHub Agent (CC4.2, CC5.3, CC6.4, CC6.8, CC7.3, CC7.5) | ✅ |
| 10c | Dashboard UI (FastAPI + dark SPA, live SSE агенты) | ✅ |
| 10d | Security hardening: API-ключ, валидация, retry, SHA-256 chain, JSON-логи | ✅ |

**Покрытие:** 33/33 контролей имеют evidence. 15 PASS / 18 FAIL (FAILы = реальные находки в sandbox).

---

## Фазы развития

### Фаза 1 — Code Quality & Security (технический долг из review)
*Закрывает: оба Code Review отчёта. Цель: production-ready codebase.*

| # | Задача | Review-источник | Приоритет |
|---|--------|-----------------|-----------|
| **11** | **constants.py + XSS-защита оркестратора (Jinja2) + subprocess → прямые импорты** | Оба отчёта, Critical | ✅ DONE |
| 12 | Alembic migrations — убрать `Base.metadata.create_all` из main.py | Оба отчёта | ✅ DONE |
| 13 | Prometheus `/metrics` + расширенный `/health` (все зависимости) | Файловый отчёт | ✅ DONE |
| 14 | Гранулярные Service Accounts (сканеры пишут, дашборд читает) | Файловый отчёт | ✅ DONE |
| — | **Тест-покрытие** (pytest, 87 тестов: constants, evidence_client, log_config, slack_notifier) | Code Review | ✅ DONE (Claude) |

### Фаза 2 — Compliance Coverage (закрыть gap с Vanta)
*Цель: поднять покрытие Vanta с 20% до 40-50%.*

| # | Задача | Контроли SOC 2 | +% к Vanta |
|---|--------|----------------|------------|
| 15 | **Continuous Scheduler** (APScheduler в ui_server) — ежедневные авто-сканы | все | ✅ DONE |
| 18 | **Quarterly Access Review UI** — workflow: менеджер → approve/revoke по списку | CC6.2, CC6.5 | ✅ DONE |
| 20 | **Policy E-Signature** (mock DocuSign webhook → evidence) | CC1.1, CC1.5 | ✅ DONE |
| 17 | **MDM Agent** (sandbox Jamf/Intune) — FileVault, EDR, screen lock | CC6.6, CC6.8 | ✅ DONE |
| 16 | **PDF Audit Report** (reportlab fallback) — экспорт всех контролей + evidence | все | ✅ DONE |
| 19 | **Vendor Risk Agent** — JSON-инвентарь + AI-анализ SOC 2 PDF вендора | CC9.2 | ✅ DONE |

### Фаза 3 — Enterprise Features
*Цель: продаваемый продукт. Текущая оценка Vanta: $1.6B.*

| # | Задача | Описание |
|---|--------|----------|
| 21 | Multi-framework (ISO 27001 маппинг) | Один контроль → несколько фреймворков | ✅ DONE |

| 22 | RBAC + JWT-сессии (Admin / Auditor / Scanner / Viewer) | Фаза 3+ | ✅ DONE |

| 23 | Auditor Portal | Отдельный readonly-вид с комментариями аудитора | ✅ DONE |

| 24 | Policy Approval Workflow | v1→v2, Change Log, подпись менеджера | ✅ DONE |
| 25 | Celery + Redis (Async Task Queue) | Оркестрация без блокировки, SLA трекинг | ✅ DONE |

### Фаза 4 — Real Integrations & Production Polish
*Цель: ~85% feature parity с Vanta. Реальные API вместо mock.*

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 26 | **Real MDM Integration** | Jamf Pro Classic API + Microsoft Intune Graph API; fallback на inventory-файл | ✅ DONE |
| 27 | **Real DocuSign Integration** | DocuSign eSignature REST API v2.1; Bearer token auth; embedded signing URL; mock fallback | ✅ DONE |
| 28 | **Jira Remediation Tickets** | Jira REST API v3 (ADF); идемпотентные тикеты для FAIL-контролей; sync статусов; mock fallback | ✅ DONE |
| 29 | **BaseHTTPClient + тесты клиентов** | `base_http_client.py` с retry/backoff; 66 новых тестов для jamf/intune/docusign клиентов | ✅ DONE |

---

## Критические находки из Code Review (не закрытые)

### Security
- [x] **XSS в `orchestrator.py`** — исправлено Jinja2 autoescape (Task 11) ✅
- [x] **Один статический API-ключ** — реализован RBAC (Task 14 ✅)
- [ ] **Секреты в `.env`** — для prod: AWS Secrets Manager / Vault

### Code Quality
- [x] **Magic strings разбросаны** — централизовано в constants.py (Task 11) ✅
- [x] **subprocess в orchestrator.py** — заменён прямыми импортами main() (Task 11) ✅
- [x] **BaseHTTPClient** — создан `base_http_client.py` с retry/timeout (Task 29) ✅
- [ ] **DRY: SlackNotifier, GitHubClient** — тесты мокируют `requests.post` напрямую, рефакторинг заблокирован ⚠️

### Observability
- [x] **`Base.metadata.create_all`** — заменён Alembic migrations (Task 12) ✅
- [x] **Нет Prometheus метрик** — добавлены /metrics + middleware + business counters (Task 13) ✅
- [ ] **Append-Only Evidence** — soft delete вместо реального удаления, SHA-цепочка ✅ частично (Task 12)

### Compliance
- [x] **MDM не интегрирован** — реализован MDM Agent + Jamf/Intune клиенты (Tasks 17, 26) ✅
- [x] **E-signature отсутствует** — DocuSign REST API v2.1 с mock fallback (Tasks 20, 27) ✅
- [x] **Policy versioning нет** — реализован PolicyWorkflow: draft→pending→approved/rejected (Task 24) ✅
- [x] **Remediation tracking** — Jira тикеты для каждого FAIL-контроля (Task 28) ✅

---

## SOC 2 Common Criteria — финальная таблица покрытия

| Код | Контроль | Агент | Статус |
|-----|----------|-------|--------|
| CC1.1 | Integrity & Ethics | survey_agent + policy_agent | ✅ PASS |
| CC1.2 | Board Oversight | policy_agent (AI draft) | ✅ PASS |
| CC1.3 | Org Structure | policy_agent (AI draft) | ✅ PASS |
| CC1.4 | Training | hr_agent + survey_agent | FAIL* |
| CC1.5 | Accountability | policy_agent (AI draft) | ✅ PASS |
| CC2.1 | Quality Info | prowler_runner (partial) | ✅ PASS |
| CC2.2 | Internal Communication | survey_agent | FAIL* |
| CC2.3 | External Communication | policy_agent | ✅ PASS |
| CC3.1 | Objectives | policy_agent | ✅ PASS |
| CC3.2 | Risk Identification | policy_agent | ✅ PASS |
| CC3.3 | Fraud Risk | policy_agent | ✅ PASS |
| CC3.4 | Change Assessment | scanner + github | FAIL* |
| CC4.1 | Ongoing Evaluations | policy_agent | ✅ PASS |
| CC4.2 | Deficiency Communication | github_agent (Issues) | ✅ PASS |
| CC5.1 | Control Selection | policy_agent | ✅ PASS |
| CC5.2 | Technology Controls | prowler_runner | ✅ PASS |
| CC5.3 | Change Management | github_agent | FAIL* |
| CC6.1 | Logical Access | scanner + prowler | FAIL* |
| CC6.2 | User Registration | scanner + hr_agent | FAIL* |
| CC6.3 | Least Privilege | scanner | FAIL* |
| CC6.4 | Physical Access | github_agent (environments) | FAIL* |
| CC6.5 | Secure Disposal | hr_agent (offboarding) | ✅ PASS |
| CC6.6 | Unauthorized Software | scanner (EC2 SG) | ✅ PASS |
| CC6.7 | Transmission Security | scanner | FAIL* |
| CC6.8 | Anti-Malware | github_agent (dependabot) | FAIL* |
| CC7.1 | Config Monitoring | scanner (CloudTrail) | FAIL* |
| CC7.2 | Anomaly Monitoring | scanner | FAIL* |
| CC7.3 | Security Events | github_agent (advisories) | FAIL* |
| CC7.4 | Incident Response | survey_agent | FAIL* |
| CC7.5 | Breach Disclosure | github_agent (SECURITY.md) | FAIL* |
| CC8.1 | Change Authorization | scanner (GitHub) | FAIL* |
| CC9.1 | Business Continuity | survey_agent | FAIL* |
| CC9.2 | Vendor Risk | hr_agent (contractors) | ✅ PASS |

> *FAIL = реальные находки в sandbox (намеренно уязвимая инфраструктура). Evidence собрано, аудит-трейл есть.

---

## Покрытие Vanta (текущее vs целевое)

| Метрика | Фаза 1-3 (Task 25) | Фаза 4 (Task 29) | Целевое |
|---------|--------|--------------|--------------|
| SOC 2 controls с evidence | 33/33 (100%) | 33/33 (100%) | 33/33 |
| Автоматизация сбора | ~65% | ~75% | ~80% |
| Покрытие Vanta feature set | ~45% | ~85% | ~90% |
| Production-readiness | ~70% | ~85% | ~90% |
| Тест-покрытие (pytest) | 211 тестов ✅ | 292 теста ✅ | — |
