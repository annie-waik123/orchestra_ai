# Orchestra AI Project Specification

Version: 1.0

Status: ✅ FROZEN

Owner: Orchestra AI

Last Updated: July 2026

---

## Purpose

This document defines the official product specification for Orchestra AI.

It describes the project's vision, scope, objectives, MVP boundaries, success criteria, and functional requirements.

This specification is frozen.

Implementation must conform to this document.

Major product changes require a Product Review before modification.
# PROJECT_SPECIFICATION.md: Orchestra AI Master Blueprint

This document represents the master engineering specification and system contract for **Orchestra AI**. Every subsystem, agent configuration, schema layout, and workspace folder structure defined herein must be strictly adhered to during development.

---

## 1. Product Vision
**Orchestra AI** is an AI Engineering Studio designed to transform a raw product idea or business requirements prompt into a complete, deployment-ready software engineering blueprint. Unlike simple conversational chatbots or localized code generators, Orchestra AI operates as a structured multi-agent workspace. By modeling the interactions of specialized software engineering roles (e.g., product managers, system architects, database designers, and security auditors) under a central orchestrator, the platform models a professional software engineering team. 

The studio delivers a coherent package of structured diagrams, API contracts, schemas, deployment configurations, and roadmaps, validated for consistency and security, giving engineers a production-grade blueprint for immediate implementation.

---

## 2. Goals & Constraints (Version 1)

### What V1 Does:
* **Requirement Distillation**: Refines ambiguous user ideas into standardized Product Requirements Documents (PRDs) and user stories.
* **Coherent Architectural Design**: Designs full system architectures and database schemas, generating both documentation and compile-ready structures (SQL scripts, OpenAPI contracts).
* **Multi-Agent Collaboration**: Orchestrates specialized agents in sequential and parallel loops using Google ADK.
* **Shared Memory Persistence**: Uses the Project Brain (Shared Memory MCP) to ensure agent alignment, eliminating context drift and token explosion.
* **Automated Quality Loops**: Runs intermediate security audits with automated feedback loops and execute syntax/lint verification in sandboxes.
* **Evaluation Gates**: Applies programmatic evaluations on the final engineering bundle before packaging.
* **Visual Workspace UI**: Renders live graph execution progress, agent decisions, and live artifact previews.

### What V1 Intentionally Does NOT Do:
* **Production Code Generation**: Does not generate the full source code (e.g., Python/Java backend logic, React UI code) of the application. It generates the *blueprint* (schemas, IaC, APIs, stories).
* **Live Cloud Deployment**: V1 generates the infrastructure blueprint (Terraform/Docker) but does not trigger live provisioning of cloud resources on AWS/GCP.
* **Automated CI/CD Execution**: Does not set up or trigger GitHub Actions or GitLab CI runners directly.
* **Interactive Wireframe Editing**: The UI displays generated diagrams but does not support drag-and-drop wireframe editing.

---

## 3. Success Criteria

A workflow execution is deemed successful only when it meets the following quantitative and qualitative criteria:
1. **Deliverable Completeness**: All 13 core deliverables defined in the folder structure are generated in the session workspace.
2. **Grammar & Syntax Validation**:
   - `openapi.yaml` passes compilation/lint checks via OpenAPI Spectral.
   - `database_schema.sql` compiles successfully against a target database driver (e.g., SQLite/PostgreSQL parser).
   - `system_flow.mermaid` and `er_diagram.mermaid` compile without syntax errors.
   - `main.tf` passes `terraform validate`.
3. **Security Audit Clearance**: The Security Review Agent logs `audit_status = PASSED` inside the Project Brain, with no unresolved findings of `severity = CRITICAL` or `HIGH`.
4. **Structured Traceability**: Every generated deliverable maps to a corresponding record in the Project Brain, detailing the author agent, dependencies, parent decisions, and confidence scores.
5. **Evaluation Threshold**: The automated Evaluator computes a composite score $S \geq 8.5/10.0$ based on completeness, consistency, security, and deployability.
6. **HITL Milestones**: The project successfully records human review and approval events at the PRD gate and the design gate.

---

## 4. User Journey

```
  [User Enters Idea]
         │
         ▼
  [Conductor Resolves Graph] ──► Initial state logged to Project Brain
         │
         ▼
  [Planning Agent Runs] ───────► Drafts PRD & User Stories ──► Hits Human Approval Gate
         │                                                            │
         ▼                                                            ▼
  [System Design Phase] ◄───────────────────────────────────── (User Approves PRD)
  ┌────────────────────────────────────────────────────────┐
  │ Parallel Execution:                                    │
  │ - System Architecture Agent (Mermaid, Layout)          │
  │ - Database Design Agent (SQL DDL, ER Diagram)          │
  └──────────────────────────┬─────────────────────────────┘
                             │
                             ▼
  [API Design Phase] ────────► Drafts OpenAPI specification
                             │
                             ▼
  [DevOps & Infra Phase] ────► Generates Dockerfile & Terraform scripts
                             │
                             ▼
  [Quality Gate Phase] ◄─────┐ Runs in parallel:
         │                   │ - Security Review Agent (Audits Security & Compliance)
         │                   │ - Evaluator (Validates Completeness, Consistency & Deployability)
         ├─► (Gate Failed?) ─┴─► Routes feedback back to target design agent to self-correct
         │
         ▼ (Gate Passed)
  [Documentation Phase] ─────► Synthesizes README & Roadmap
         │
         ▼
  [Final Blueprint Release] ──► ZIP package & Git tag compiled
```

1. **Intake**: The user submits a raw prompt in the Studio (e.g., "I want to build a marketplace for local tool rentals").
2. **Analysis**: The Orchestra Conductor processes the request, initializes the Project Brain with session tokens, and spawns the execution DAG.
3. **Planning & Approval**: The Planning Agent writes `01_prd.md` and `02_user_stories.md`. The workflow pauses. The user inspects the requirements in the UI and clicks "Approve."
4. **Coordinated Design**: The System Architecture and Database Design agents run in parallel. They write blueprints to the workspace and log decisions to the Project Brain. The API Design Agent runs next, using the schemas to define OpenAPI contracts.
5. **Infrastructure Drafting**: The DevOps Agent writes Docker configurations and Terraform infrastructure blueprints.
6. **Quality Gate**: The Security Review Agent and the Evaluator run in parallel to review the workspace. If the Security Review detects vulnerabilities (e.g., plaintext passwords) or the Evaluator finds consistency mismatches (e.g., mismatched API-to-DB models) or low scores ($S < 8.5$), the Quality Gate fails. Structured feedback is posted to the Project Brain, and control is routed back to the appropriate design agent.
7. **Documentation & Release**: Once the Quality Gate is passed, the Documentation Agent compiles the `README.md` and `13_development_roadmap.md`. Finally, the Conductor zips the workspace, creates a Git release tag, and exposes it for download.

---

## 5. Agent Responsibilities

| Agent Name | Mission | Core Inputs | Core Outputs | Skills Used | MCP Tools Used | Project Brain Read Keys | Project Brain Write Keys |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Orchestra Conductor** | Orchestrates tasks, coordinates state, and manages client execution flow. | User prompt, task results, human inputs. | Workflow state, task DAG allocations. | `orchestration_management`, `human_collaboration` | `brain_write_session`, `brain_read_session`, `fs_list_files` | `*` | `session_state`, `active_task`, `human_decisions` |
| **Planning Agent** | Establishes requirements, roadmap timelines, and user stories. | User prompt, Conductor input. | `01_prd.md`, `02_user_stories.md`, `13_roadmap.md` | `prd_generation`, `user_story_authoring` | `fs_write_file`, `brain_write_decisions` | `product_vision` | `prd_spec`, `user_stories`, `roadmap_details` |
| **System Architecture Agent** | Maps components, defines tech stacks, and designs layout flows. | PRD, User Stories. | `03_architecture.md`, `04_system_flow.mermaid` | `architecture_design`, `mermaid_rendering` | `fs_write_file`, `brain_write_decisions`, `sandbox_validate` | `prd_spec`, `user_stories` | `system_architecture_decisions`, `architecture_diagrams` |
| **Database Design Agent** | Structures relational schemas, ER diagrams, and constraints. | PRD, User Stories, Architecture designs. | `05_database_schema.sql`, `06_er_diagram.mermaid` | `database_modeling`, `er_modeling` | `fs_write_file`, `brain_write_decisions`, `sandbox_lint_sql` | `prd_spec`, `user_stories`, `system_architecture_decisions` | `database_schema_details`, `er_diagrams` |
| **API Design Agent** | Outlines OpenAPI schemas, endpoints, and data payloads. | PRD, Architecture, Database design. | `07_openapi_specification.yaml` | `openapi_design`, `api_contracting` | `fs_write_file`, `brain_write_decisions`, `sandbox_lint_api` | `prd_spec`, `system_architecture_decisions`, `database_schema_details` | `api_contracts` |
| **Security Review Agent** | Threat-models, audits schemas/designs, and issues security audits. | Blueprint artifacts, design logs. | `11_security_audit_report.md`, feedback critiques. | `security_threat_modeling`, `compliance_auditing` | `fs_read_file`, `brain_write_decisions`, `brain_write_audits` | `system_architecture_decisions`, `database_schema_details`, `api_contracts`, `infra_blueprints` | `security_findings`, `audit_status` |
| **DevOps & Deployment Agent** | Configures container configs and constructs Terraform infrastructure blueprints. | Architecture, DB Schema, API contracts. | `08_infra_plan.md`, `09_Dockerfile`, `10_main.tf` | `docker_configuration`, `terraform_authoring` | `fs_write_file`, `brain_write_decisions`, `sandbox_lint_tf` | `prd_spec`, `system_architecture_decisions`, `database_schema_details` | `infra_blueprints` |
| **Documentation Agent** | Formulates system READMEs and compiles development blueprints. | Project Brain logs, all workspace files. | `12_README.md` | `readme_synthesis`, `technical_documentation` | `fs_write_file`, `brain_read_all` | `*` | `final_documentation` |

---

## 6. Project Brain Specification (Memory Schema)

The Project Brain runs as an in-memory/JSON-file database accessed via Model Context Protocol. Below is the specification schema shown in representative JSON payloads.

### 6.1 Project & Session Metadata
```json
{
  "project_id": "proj-90182",
  "name": "Orchestra RentTool",
  "created_at": "2026-06-26T12:00:00Z",
  "status": "IN_PROGRESS",
  "session": {
    "session_id": "sess-6c535085",
    "git_commit_hash": "a1b2c3d4e5f6g7h8",
    "active_node": "api_design_node",
    "human_feedback_log": [
      {
        "timestamp": "2026-06-26T12:05:00Z",
        "checkpoint": "PRD_GATE",
        "status": "APPROVED",
        "comments": "Ensure rental duration constraints are enforced in user stories."
      }
    ]
  }
}
```

### 6.2 Agent Decisions & Artifact Schema
```json
{
  "decisions": [
    {
      "decision_id": "dec-db-001",
      "node": "database_design_node",
      "agent": "Database Design Agent",
      "timestamp": "2026-06-26T12:12:30Z",
      "title": "Selection of PostgreSQL as primary datastore",
      "rationale": "Requirement PRD-04 outlines high relational transactional integrity for payment processing. Non-relational options rejected due to lack of native ACID transaction compliance on multi-row actions.",
      "alternatives_considered": ["MongoDB", "SQLite"],
      "confidence_score": 0.95,
      "dependencies": ["dec-arch-003"],
      "artifacts_produced": [
        {
          "file_path": "workspace/05_database_schema.sql",
          "checksum": "sha256-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
          "type": "sql_schema"
        },
        {
          "file_path": "workspace/06_er_diagram.mermaid",
          "checksum": "sha256-f5c889f8173ab19128de163351d34c1a2f6fb39f",
          "type": "diagram"
        }
      ]
    }
  ]
}
```

### 6.3 Security Audit & Findings
```json
{
  "security_audits": [
    {
      "audit_id": "sec-aud-004",
      "target_node": "api_design_node",
      "timestamp": "2026-06-26T12:16:10Z",
      "status": "FAILED",
      "findings": [
        {
          "finding_id": "find-sec-01",
          "file": "workspace/07_openapi_specification.yaml",
          "line": 42,
          "severity": "HIGH",
          "vulnerability_type": "Missing Authentication Gate",
          "description": "Endpoint '/api/v1/rentals/{id}' allows HTTP DELETE operations without authorization headers defined in the security scheme.",
          "mitigation_plan": "Add security binding matching JWT bearer schemes to endpoint paths."
        }
      ]
    }
  ]
}
```

### 6.4 Evaluation Results
```json
{
  "evaluation_gate": {
    "evaluated_at": "2026-06-26T12:25:00Z",
    "composite_score": 8.8,
    "pass": true,
    "metrics": {
      "completeness": 1.0,
      "consistency": 0.9,
      "security": 0.8,
      "documentation_quality": 0.9,
      "deployability": 0.8
    },
    "logs": [
      "All 13 deliverables identified in workspace directory.",
      "OpenAPI spec validated successfully against Spectral.",
      "Terraform init/validate passed in sandbox."
    ]
  }
}
```

---

## 7. MCP Architecture

The Model Context Protocol acts as the security boundary and API engine for the studio's tools.

```
       ┌─────────────────────────────────────────────────┐
       │                  MCP Gateway                    │
       └─────┬─────────────────┬───────────────────┬─────┘
             │                 │                   │
             ▼                 ▼                   ▼
     ┌───────────────┐ ┌───────────────┐   ┌───────────────┐
     │  Filesystem   │ │ Project Brain │   │    Sandbox    │
     │  MCP Server   │ │  MCP Server   │   │  MCP Server   │
     └───────────────┘ └───────────────┘   └───────────────┘
```

### 7.1 Filesystem MCP
* **Purpose**: Sandboxed access to the session workspace folder.
* **Tools Exposed**:
  - `read_file(path)`: Reads the content of a file.
  - `write_file(path, content)`: Creates or overwrites a file.
  - `append_file(path, content)`: Appends information.
  - `list_directory(path)`: Returns a directory structure tree.
  - `get_file_diffs(path)`: Shows Git diff state of files.

### 7.2 Project Brain MCP
* **Purpose**: Coordinates structured read/write access to the central session memory database.
* **Tools Exposed**:
  - `write_decision(payload)`: Saves an agent's choices, arguments, and metadata.
  - `get_decisions(filter_node)`: Retrieves past decisions.
  - `write_audit_report(payload)`: Logs security audits.
  - `get_audit_findings(filter_node)`: Retrieves pending vulnerabilities.
  - `write_evaluation(payload)`: Saves metrics scores.
  - `get_session_state()`: Fetches global metadata.

### 7.3 Sandbox MCP
* **Purpose**: Executes verification checks inside isolated Docker container sandboxes.
* **Tools Exposed**:
  - `validate_openapi(file_path)`: Runs Spectral linter.
  - `lint_sql_schema(file_path)`: Evaluates syntax against parser standards.
  - `validate_terraform(file_path)`: Runs `terraform validate` and `tflint`.
  - `validate_mermaid(file_path)`: Ensures diagrams are syntax-correct.

### 7.4 Developer Knowledge MCP
* **Purpose**: Exposes reference guides, API templates, design patterns, and boilerplate schemas to reduce generation hallucination.
* **Tools Exposed**:
  - `search_best_practices(query)`: Retrieves verified engineering patterns.
  - `get_template(technology)`: Returns standard starting configurations.

### 7.5 Future GitHub MCP (Version 2)
* **Purpose**: Integrates with team repositories.
* **Tools Exposed**:
  - `create_repository(repo_name)`
  - `push_blueprint_branch(branch_name)`
  - `open_pull_request(title, body)`

### 7.6 Future Cloud MCP (Version 3)
* **Purpose**: Provisions preview environments.
* **Tools Exposed**:
  - `deploy_infrastructure(terraform_file)`
  - `get_deploy_status(deployment_id)`

---

## 8. Agent Skills

Agent Skills are configured as standalone packages containing instructions (`SKILL.md`), checking scripts (`scripts/`), and examples.

### 8.1 `prd_generation` (Planning Agent)
* **Purpose**: Extracts business scope from unstructured concepts.
* **Trigger**: Conductor passes starting request.
* **Expected Output**: Formatted markdown PRD file outlining goals, user flows, and metrics.
* **Referenced Scripts**: `scripts/validate_prd_format.py` (checks header structures).
* **Artifacts Produced**: `01_prd.md`

### 8.2 `user_story_authoring` (Planning Agent)
* **Purpose**: Drafts actionable developer user stories and roadmaps.
* **Trigger**: Completion of PRD.
* **Expected Output**: Structured stories following Gherkin formats.
* **Referenced Scripts**: None.
* **Artifacts Produced**: `02_user_stories.md`, `13_development_roadmap.md`

### 8.3 `architecture_design` (System Architecture Agent)
* **Purpose**: Maps application logic, microservices, caches, and system interactions.
* **Trigger**: PRD approval event.
* **Expected Output**: Markdown layout documenting architectural components and choices.
* **Referenced Scripts**: None.
* **Artifacts Produced**: `03_architecture_design.md`

### 8.4 `mermaid_rendering` (System Architecture & Database Agents)
* **Purpose**: Formulates visual flowcharts and ER layouts.
* **Trigger**: System block definition.
* **Expected Output**: Compile-ready Mermaid file.
* **Referenced Scripts**: `scripts/mermaid_syntax_check.py` (tests parsing).
* **Artifacts Produced**: `04_system_flow.mermaid`, `06_er_diagram.mermaid`

### 8.5 `database_modeling` (Database Design Agent)
* **Purpose**: Designs relational SQL schemas.
* **Trigger**: Architectural boundary definition.
* **Expected Output**: Clear DDL SQL script containing keys, indexes, and schemas.
* **Referenced Scripts**: `scripts/sql_linter.py` (runs parsing dry runs).
* **Artifacts Produced**: `05_database_schema.sql`

### 8.6 `openapi_design` (API Design Agent)
* **Purpose**: Designs RESTful web services contract structures.
* **Trigger**: Database schema completion.
* **Expected Output**: OpenAPI 3.1 YAML file.
* **Referenced Scripts**: `scripts/run_spectral_linter.sh` (validates spec standards).
* **Artifacts Produced**: `07_openapi_specification.yaml`

### 8.7 `security_threat_modeling` (Security Review Agent)
* **Purpose**: Audits specifications for data leakage, access leaks, and credentials.
* **Trigger**: Artifact generation lifecycle hooks.
* **Expected Output**: Vulnerability reports and design corrections.
* **Referenced Scripts**: `scripts/check_sec_vulnerabilities.py` (regex matches patterns).
* **Artifacts Produced**: `11_security_audit_report.md`

### 8.8 `docker_configuration` (DevOps Agent)
* **Purpose**: Generates multi-stage build container configurations.
* **Trigger**: System architecture design completion.
* **Expected Output**: Deployment-ready Dockerfile.
* **Referenced Scripts**: `scripts/hadolint_check.sh`.
* **Artifacts Produced**: `09_Dockerfile`

### 8.9 `terraform_authoring` (DevOps Agent)
* **Purpose**: Structures infrastructure-as-code files.
* **Trigger**: System architecture design completion.
* **Expected Output**: Terraform scripts detailing cloud boundaries.
* **Referenced Scripts**: `scripts/validate_tf.sh`.
* **Artifacts Produced**: `10_main.tf`

---

## 9. ADK Workflow & Execution Graph

Google ADK manages the runtime states. The workflow graph execution details are defined below:

```
[init] -> [planning] -> [PRD Gate] -> [design_parallel] -> [api_design] -> [devops] -> [quality_gate] -> [docs] -> [release]
```

### Node-by-Node Execution Logic

1. **`init_node` (Sequential)**:
   - Conductor parses inputs. Creates project records in Project Brain. Routes flow to `planning_node`.

2. **`planning_node` (Sequential)**:
   - Planning Agent runs `prd_generation` and `user_story_authoring` skills. Saves deliverables. Halts on `PRD_GATE`.
   - **PRD Gate**: Halts graph. Sends WebSocket event to UI console. If user approves, execution resumes. If user rejects, inputs are appended and `planning_node` re-runs.

3. **`design_parallel_node` (Parallel Branches)**:
   - **Branch A**: System Architecture Agent executes `architecture_design` and `mermaid_rendering` skills. Writes to `03_architecture_design.md` and `04_system_flow.mermaid`.
   - **Branch B**: Database Design Agent executes `database_modeling` and `mermaid_rendering` skills. Writes to `05_database_schema.sql` and `06_er_diagram.mermaid`.
   - *Synchronization*: Both branches must complete before the workflow routes to `api_design_node`.

4. **`api_design_node` (Sequential)**:
   - API Design Agent reads system and database designs from the Project Brain. Generates `openapi.yaml`. Routes to `devops_node`.

5. **`devops_node` (Sequential)**:
   - DevOps Agent writes container configs and IaC blueprints. Writes to `08_infra_plan.md`, `09_Dockerfile`, and `10_main.tf`. Routes to `quality_gate_node`.

6. **`quality_gate_node` (Parallel checks / Conditional Retry Loop)**:
   - Executes two validation pipelines concurrently:
     - **Security Check**: Security Review Agent scans workspace files and reads Project Brain decisions, running checks for secrets, access configuration, and threat modeling.
     - **Evaluation**: Evaluator calculates score $S$ based on completeness, consistency, and deployability.
   - **Condition / Routing Logic**:
     - If security findings contain `severity = HIGH/CRITICAL` OR evaluation score $S < 8.5$:
       - Sets state `quality_gate = FAILED`.
       - Logs audit failures and scoring breakdown to Project Brain.
       - Identifies target design node (e.g. database design or DevOps node) that caused the check to fail.
       - Routes control *back* to the target node.
       - Increments retry counter. Max retries = 3 (if exceeded, stops execution and raises a block for human intervention).
     - If security checks pass and $S \ge 8.5$:
       - Sets state `quality_gate = PASSED`.
       - Routes control to `docs_node`.

7. **`docs_node` (Sequential)**:
   - Documentation Agent compiles the README and roadmap. Routes to `release_node`.

8. **`release_node` (Terminal)**:
   - Conductor packages the workspace folder into a tagged release zip file and exposes it to the client.

---

## 10. Folder Structure

The production project directory structure is laid out as follows:

```
orchestra_ai/
├── app/                            # Backend FastAPI Server
│   ├── main.py                     # Entry point
│   ├── engine.py                   # Orchestra Execution Core
│   └── routers/                    # API Endpoints (session, ws, approval)
├── agents/                         # Agent Class Definitions (ADK Based)
│   ├── conductor.py
│   ├── planner.py
│   ├── architect.py
│   ├── database_designer.py
│   ├── api_designer.py
│   ├── security_reviewer.py
│   ├── devops.py
│   └── documenter.py
├── skills/                         # Antigravity Reusable Agent Skills
│   ├── prd_generation/
│   │   ├── SKILL.md
│   │   └── scripts/validate_prd.py
│   ├── user_story_authoring/
│   │   └── SKILL.md
│   ├── architecture_design/
│   │   └── SKILL.md
│   ├── database_modeling/
│   │   ├── SKILL.md
│   │   └── scripts/sql_lint.sh
│   ├── openapi_design/
│   │   ├── SKILL.md
│   │   └── scripts/lint_openapi.sh
│   ├── security_threat_modeling/
│   │   ├── SKILL.md
│   │   └── scripts/run_checks.py
│   ├── docker_configuration/
│   │   └── SKILL.md
│   └── terraform_authoring/
│       └── SKILL.md
├── mcp/                            # Model Context Protocol Servers
│   ├── filesystem_server.py        # Workspace sandbox FS controls
│   ├── brain_server.py             # Memory SQLite backend server
│   └── sandbox_server.py           # Docker environment runner interface
├── brain/                          # Storage directory for Project Brain sessions
│   └── metadata.db                 # SQLite memory database schema
├── artifacts/                      # Session execution outputs (The Blueprint)
│   └── templates/                  # Base document schemas
├── ui/                             # React/Next.js Studio Frontend
│   ├── components/                 # Graph visualizer, timeline, previewers
│   └── pages/                      # Main studio canvas
├── docs/                           # Documentation and Kaggle Submission guides
├── tests/                          # Integration and Unit testing suites
└── config/                         # System environment and agent configs
```

---

## 11. Technology Stack Selection Rationale

* **Google ADK**: Provides native workflow abstractions (DAG routing, loop retries, parallel branches) designed for complex LLM executions, replacing manual script orchestration.
* **Gemini (3.5 Pro/Flash)**:
  - **Gemini 3.5 Pro** offers reasoning capabilities and handles large diagrams/architectures.
  - **Gemini 3.5 Flash** handles fast tasks (lint iterations, drafting user stories, documentation synthesis).
  - The **2 Million token context window** is critical for loading entire workspace states to check consistency without context truncation.
* **Antigravity Paradigms**: Provides a structured format for organizing agent capabilities (Skills) and managing independent sandboxed worktree environments.
* **Model Context Protocol (MCP)**: Establishes a standard protocol to isolate agent prompts from raw database/API calls, ensuring modularity and security.
* **FastAPI**: A high-performance Python web framework used to expose endpoints and manage WebSocket channels for streaming execution updates to the UI.
* **React / Next.js**: Renders responsive visual dashboards and dynamic DAG visualizations.
* **Docker**: Provides sandbox isolation to compile code, run linters, and validate scripts.
* **Terraform**: The industry standard for infrastructure definition, ensuring the cloud layouts generated are valid.
* **Git**: Embedded in the Workspace Filesystem to track changes, support diff analysis, and enable rollback capabilities.

---

## 12. Future Roadmap

### Version 2: VCS Integration & Interactive Mocking
* **Workspace VCS Integration**: Direct integration with GitHub/GitLab, allowing agents to push generated blueprints, open pull requests, and resolve review comments.
* **Interactive Code Mocking**: Generating mock endpoints in Node/Python, deploying them locally in the Docker Sandbox, and letting users call API routes directly from the Studio interface to test the design.
* **Collaborative Visual Editing**: Enabling users to click component blocks in the diagram and type changes (e.g., "Add Redis cache here"), prompting the system to rewrite the architecture documents automatically.

### Version 3: Autonomous Deployment & Simulation
* **One-Click Cloud Provisioning**: Deploying the validated Terraform configuration to staging sandboxes (AWS/GCP) automatically.
* **AI-Driven Chaos Testing & Red Teaming**: Spawning autonomous attack agents inside the sandbox to perform vulnerability scanning (e.g., SQL injections, credential stuffing) against mock APIs, logging reports back to the Project Brain for continuous design optimization.
* **Cost & SLA Simulation**: Simulating traffic spikes on the generated infrastructure configuration, estimating cloud bills, and recommending scale-in/scale-out index adjustments.
