# PROJECT_BRAIN_HANDOVER.md: Memory System Engineering Handover

This document serves as the technical handover and integration guide for the **Project Brain** component of Orchestra AI. It contains architectural layouts, API specifications, MCP tool documentation, schemas, and extension points to guide future implementations.

---

## 1. System Architecture

The Project Brain is designed as a decoupled, multi-layer memory storage backend:

```
┌────────────────────────────────────────────────────────┐
│                        FastAPI                         │
│  - REST HTTP Endpoints under /api/v1/...               │
│  - Configured middlewares & controllers                │
└───────────┬────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│                     BrainService                       │
│  - Handles version increment logic                     │
│  - Coordinates audit logger and state updates          │
└───────────┬────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│                   Base Repository                      │
│  - Abstract Base Class interfaces (base.py)            │
│  - Loose coupling to plug database backends            │
└───────────┬────────────────────────────────────────────┘
            │
            ▼
┌────────────────────────────────────────────────────────┐
│                    JSON persistence                    │
│  - Read/Write key-value documents in storage/          │
│  - Thread-safe access utilizing threading.Lock         │
└────────────────────────────────────────────────────────┘
```

* **Filesystem Isolation**: Standard V1 implementation stores files under `brain/storage/` in JSON format.
* **FastAPI Entry Point**: Handled in [brain/main.py](file:///d:/Projects/orchestra_ai/brain/main.py).
* **MCP Server**: Handled in [mcp/brain_server.py](file:///d:/Projects/orchestra_ai/mcp/brain_server.py) using the FastMCP framework, providing direct access to the `BrainService` layer.

---

## 2. Pydantic Data Models

All data models utilize Pydantic V2 schemas found in [brain/schemas/](file:///d:/Projects/orchestra_ai/brain/schemas).

### 2.1 Project
* **Purpose**: Declares project metadata.
* **Fields**:
  - `id`: Unique generated identifier (`proj-*`).
  - `name`: Text identifier.
  - `description`: Optional detail string.
  - `created_at`: Timestamp.
  - `status`: `active`, `completed`, or `archived`.

### 2.2 Session
* **Purpose**: Tracks active execution workflows.
* **Fields**:
  - `id`: Session run identifier (`sess-*`).
  - `project_id`: Foreign key reference to target project.
  - `created_at`: Timestamp.
  - `git_commit_hash`: Optional string reference.
  - `active_node`: Current workflow node name.
  - `status`: `IN_PROGRESS`, `SUCCESS`, or `FAILED`.
  - `dag`: Structured metadata mapping nodes, dependency edges, and activity history.

### 2.3 Artifact
* **Purpose**: Represents files generated during the session. Includes version increments and dependency structures.
* **Fields**:
  - `id`: Generated uuid identifier.
  - `session_id`: Session association identifier.
  - `file_path`: Workspace relative file path.
  - `version`: Version number (starts at 1, increments on new writes to the same path).
  - `checksum`: SHA-256 hash.
  - `type`: Category indicator (e.g., `prd`, `sql_schema`, `openapi_spec`).
  - `generated_by`: Name of author agent.
  - `depends_on`: List of parent file paths/artifact IDs.
  - `used_by`: List of agent names consuming this file.

### 2.4 Decision
* **Purpose**: Documents key design decisions.
* **Fields**:
  - `id`: Generated identifier (`dec-*`).
  - `session_id`: Session reference.
  - `node`: workflow graph node name.
  - `agent`: Author agent name.
  - `timestamp`: Creation time.
  - `title`: Description of choice.
  - `rationale`: Justifications and trade-offs.
  - `alternatives_considered`: Array of choices rejected.
  - `confidence_score`: Float between 0.0 and 1.0.
  - `dependencies`: Earlier decision IDs this choice relies on.
  - `artifacts_produced`: List of generated file paths.

### 2.5 Evaluation
* **Purpose**: Stores Quality Gate metrics.
* **Fields**:
  - `session_id`: Associated session.
  - `evaluated_at`: Timestamp.
  - `completeness`, `consistency`, `security`, `documentation_quality`, `deployability`: Metric structures containing score and detail text.
  - `composite_score`: Float out of 10.0.
  - `passed`: Boolean validation flag.
  - `logs`: Log list trace.
  - `findings`: List of dict error outputs.

### 2.6 Agent Registry
* **Purpose**: Stores active specialist agent specifications.
* **Fields**:
  - `name`: Unique key (e.g. Planning Agent).
  - `description`: Scope of operations.
  - `status`: `active` or `inactive`.
  - `system_prompt`: Core instructions.
  - `inputs`: Context requirement filters.
  - `outputs`: Expected deliverables.
  - `skills`: Skill names associated.
  - `mcp_servers`: Required tool bindings.

---

## 3. API Endpoints

### Projects
* `POST /api/v1/projects`: Creates a project.
* `GET /api/v1/projects/{project_id}`: Retrieves metadata.
* `GET /api/v1/projects`: Lists all profiles.

### Sessions
* `POST /api/v1/sessions`: Instantiates a session.
* `GET /api/v1/sessions/{session_id}`: Retrieves active workflow detail.
* `PATCH /api/v1/sessions/{session_id}`: Modifies state variables and execution DAG nodes.
* `GET /api/v1/sessions/{session_id}/context?agent_name={agent}`: Returns dynamic context compilation.

### Artifacts
* `POST /api/v1/artifacts`: Registers an artifact.
* `GET /api/v1/artifacts/{artifact_id}`: Reads metadata.
* `GET /api/v1/artifacts/session/{session_id}`: List latest active artifacts.
* `GET /api/v1/artifacts/session/{session_id}/versions?file_path={path}`: Lists all version updates for a path.

### Decisions
* `POST /api/v1/decisions`: Registers design decisions.
* `GET /api/v1/decisions/session/{session_id}`: Lists decisions chronologically.

### Evaluations
* `POST /api/v1/evaluations`: Commits Quality Gate validation outputs.
* `GET /api/v1/evaluations/session/{session_id}`: Reads score reports.

### Agent Registry
* `POST /api/v1/agents`: Registers specialist agent metadata.
* `GET /api/v1/agents/{name}`: Fetches active system prompts.
* `GET /api/v1/agents`: Lists registered specialists.

---

## 4. MCP Tools Expose Matrix

The FastMCP server ([mcp/brain_server.py](file:///d:/Projects/orchestra_ai/mcp/brain_server.py)) exposes stdio bindings:

| Tool Name | Parameters | Returns | Description |
| :--- | :--- | :--- | :--- |
| `register_agent` | `name`, `description`, `system_prompt`, `inputs`, `outputs`, `skills`, `mcp_servers` | JSON Response | Adds specialist configurations. |
| `create_project` | `name`, `description` | JSON Response | Instantiates project profile. |
| `create_session` | `project_id`, `git_commit_hash`, `dag` | JSON Response | Instantiates execution session context. |
| `update_session_state`| `session_id`, `active_node`, `status`, `git_commit_hash`, `dag` | JSON Response | Updates session metadata. |
| `store_artifact` | `session_id`, `file_path`, `checksum`, `type`, `generated_by`, `depends_on`, `used_by` | JSON Response | Commits artifact, version increments automatic. |
| `store_decision` | `session_id`, `node`, `agent`, `title`, `rationale`, `confidence_score`, `alternatives_considered`, `dependencies`, `artifacts_produced` | JSON Response | Stores design choices. |
| `store_evaluation` | `session_id`, `completeness_score/details`, `consistency_score/details`, `security_score/details`, `documentation_quality_score/details`, `deployability_score/details`, `composite_score`, `passed`, `logs`, `findings` | JSON Response | Records quality validation checks. |
| `get_agent_context` | `session_id`, `agent_name` | Markdown String | **Context Injection Engine**: Fetches tailored inputs. |
| `log_audit_action` | `session_id`, `agent`, `action`, `details` | JSON Response | Adds audit transaction records. |

---

## 5. Context Injection Engine

A crucial feature of the Project Brain is the **Context Builder** in [brain/services/context_builder.py](file:///d:/Projects/orchestra_ai/brain/services/context_builder.py).
Agents call this service before starting a task. The engine:
1. Resolves agent requirements via the Agent Registry.
2. Filters session decisions and artifacts.
3. Formulates a structured markdown prompt context.

This ensures agents remain aligned on design decisions and artifact dependencies without overloading their context window with raw chat history.

---

## 6. Integration & Extension Guidance

### 6.1 Plugging SQL Databases
The code uses ABC interfaces in [brain/repository/base.py](file:///d:/Projects/orchestra_ai/brain/repository/base.py) and dependency injection.
To migrate to PostgreSQL or SQLite:
1. Create `brain/repository/sql_repo.py` inheriting from base repository classes.
2. Implement SQL operations using SQLAlchemy.
3. Update [brain/services/brain_service.py](file:///d:/Projects/orchestra_ai/brain/services/brain_service.py) (or FastAPI dependencies) to instantiate the SQL repository:
   ```python
   # Example change inside brain_service.py:
   # self.project_repo = SQLProjectRepository(db_session)
   ```

### 6.2 Binding Google ADK Workflow
During Google ADK agent execution, bind tools by passing the MCP server configurations. For example, during conductor initialize:
```python
# During session creation
session = mcp_client.call_tool("create_session", {"project_id": "proj-123"})
```
Before executing a specialist task:
```python
# Fetch agent-tailored context and inject it into the prompt
context = mcp_client.call_tool("get_agent_context", {"session_id": session_id, "agent_name": "Database Design Agent"})
# Prompt = System Prompt + Context + Task Instructions
```
Upon completing a task, store decisions and artifacts:
```python
mcp_client.call_tool("store_artifact", {
    "session_id": session_id,
    "file_path": "05_database_schema.sql",
    "checksum": "...",
    "type": "sql_schema",
    "generated_by": "Database Design Agent"
})
```
