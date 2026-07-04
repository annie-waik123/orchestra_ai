import time
from typing import List, Dict, Any, Optional
from agents.models import ToolError, ConfigurationError
from agents.metrics import MetricsCollector

class ToolManager:
    """
    Facade mediating access to Model Context Protocol (MCP) servers.
    Enforces manifest-declared tool constraints, normalizes server exceptions,
    and aggregates latency metrics.
    """
    def __init__(
        self, 
        allowed_mcp_servers: List[str], 
        metrics: MetricsCollector,
        mcp_client_resolver: Optional[Any] = None
    ):
        self.allowed_servers = [s.lower() for s in allowed_mcp_servers]
        self.metrics = metrics
        self.mcp_client_resolver = mcp_client_resolver
        self._is_open = False
        
        from agents.sandbox_manager import DockerSandboxManager
        self.sandbox_manager = DockerSandboxManager()
        
        # Verify allowed servers mappings
        # (Capabilities map directly to required servers)
        self._server_map = {
            "read_workspace_file": "filesystem",
            "write_workspace_file": "filesystem",
            "list_workspace_files": "filesystem",
            "execute_in_sandbox": "sandbox",
            "validate_sql": "sandbox",
            "validate_openapi": "sandbox",
            "validate_mermaid": "sandbox",
            "query_developer_knowledge": "developer_knowledge"
        }

    def _check_allowed(self, capability: str):
        required_server = self._server_map.get(capability)
        if not required_server:
            raise ConfigurationError(f"Unknown capability: {capability}")
        if required_server not in self.allowed_servers:
            raise ConfigurationError(
                f"Capability '{capability}' requires server '{required_server}', "
                f"which is not declared in manifest allowed_mcp_servers: {self.allowed_servers}"
            )

    def open(self):
        """Initializes client bindings and connections."""
        self._is_open = True

    def close(self):
        """Disconnects client bindings and releases resources."""
        self._is_open = False

    def _execute_tool_call(self, capability: str, server: str, tool_name: str, args: Dict[str, Any]) -> Any:
        self._check_allowed(capability)
        if not self._is_open:
            raise ConfigurationError("ToolManager is not open. Call open() first.")

        start_time = time.time()
        success = False
        try:
            # Execute logic using resolver or mock client
            if self.mcp_client_resolver:
                result = self.mcp_client_resolver.call_tool(server, tool_name, args)
            else:
                # If no resolver is injected, we assume stub behavior for testing
                result = f"Stub response for {server}/{tool_name}"
            success = True
            return result
        except Exception as e:
            # Normalize error to ToolError
            raise ToolError(
                capability=capability,
                server=server,
                cause=str(e),
                recoverable_hint=self._guess_recoverability(e)
            ) from e
        finally:
            latency = (time.time() - start_time) * 1000.0
            self.metrics.record_tool_call(capability, latency, success)

    def _guess_recoverability(self, exception: Exception) -> bool:
        # Normalizes error to decide if transient
        err_msg = str(exception).lower()
        if "timeout" in err_msg or "rate limit" in err_msg or "429" in err_msg or "busy" in err_msg:
            return True
        return False

    # --- Capability Methods ---

    def read_workspace_file(self, path: str) -> str:
        """Reads workspace file content from Filesystem MCP."""
        res = self._execute_tool_call("read_workspace_file", "filesystem", "read_file", {"path": path})
        if isinstance(res, dict) and "content" in res:
            return res["content"]
        return str(res)

    def write_workspace_file(self, path: str, content: str):
        """Writes content to workspace via Filesystem MCP."""
        self._execute_tool_call("write_workspace_file", "filesystem", "write_file", {"path": path, "content": content})

    def list_workspace_files(self, pattern: str) -> List[str]:
        """Queries matching paths from Filesystem MCP."""
        res = self._execute_tool_call("list_workspace_files", "filesystem", "list_files", {"pattern": pattern})
        if isinstance(res, list):
            return res
        return []

    def execute_in_sandbox(self, command: str, files: Dict[str, str]) -> Dict[str, Any]:
        """Runs isolated execution shell via Sandbox MCP or Docker sandbox."""
        self._check_allowed("execute_in_sandbox")
        
        import time
        start_time = time.time()
        success = False
        duration_ms = 0

        if self.sandbox_manager.is_enabled():
            try:
                result = self.sandbox_manager.execute(command, files)
                success = result.get("status") == "success"
                duration_ms = result.get("duration_ms", 0)
                
                # Accumulate sandbox time in Redis
                from brain.database import current_session_id
                session_id = current_session_id.get()
                if session_id and duration_ms > 0:
                    try:
                        from job_queue.redis_client import RedisClient
                        r_client = RedisClient().client
                        key = f"sandbox_time:{session_id}"
                        curr = r_client.get(key)
                        r_client.set(key, str((int(curr) if curr else 0) + duration_ms))
                    except Exception:
                        pass
                
                return result
            except Exception as e:
                # Lazy import ToolError to avoid circular import issues
                from agents.models import ToolError
                raise ToolError(
                    capability="execute_in_sandbox",
                    server="sandbox",
                    cause=f"Docker sandbox execution failed: {e}",
                    recoverable_hint=False
                ) from e
            finally:
                latency = (time.time() - start_time) * 1000.0
                self.metrics.record_tool_call("execute_in_sandbox", latency, success)

        res = self._execute_tool_call("execute_in_sandbox", "sandbox", "execute_command", {"command": command, "files": files})
        duration_ms = int((time.time() - start_time) * 1000.0)
        
        # Accumulate sandbox fallback time in Redis
        from brain.database import current_session_id
        session_id = current_session_id.get()
        if session_id:
            try:
                from job_queue.redis_client import RedisClient
                r_client = RedisClient().client
                key = f"sandbox_time:{session_id}"
                curr = r_client.get(key)
                r_client.set(key, str((int(curr) if curr else 0) + duration_ms))
            except Exception:
                pass

        if isinstance(res, dict):
            return res
        return {"stdout": str(res), "stderr": "", "exit_code": 0}

    def validate_sql(self, schema: str) -> Dict[str, Any]:
        """Validates relational DDL syntax using Sandbox SQL parser/linter."""
        res = self._execute_tool_call("validate_sql", "sandbox", "lint_sql", {"schema": schema})
        if isinstance(res, dict):
            return res
        return {"valid": True, "errors": []}

    def validate_openapi(self, spec: str) -> Dict[str, Any]:
        """Runs spectral YAML validation checks via Sandbox OpenAPI linter."""
        res = self._execute_tool_call("validate_openapi", "sandbox", "lint_openapi", {"spec": spec})
        if isinstance(res, dict):
            return res
        return {"valid": True, "errors": []}

    def validate_mermaid(self, diagram: str) -> Dict[str, Any]:
        """Ensures diagrams parse syntax checks via Sandbox Mermaid parser."""
        res = self._execute_tool_call("validate_mermaid", "sandbox", "lint_mermaid", {"diagram": diagram})
        if isinstance(res, dict):
            return res
        return {"valid": True, "errors": []}

    def query_developer_knowledge(self, topic: str) -> List[Dict[str, Any]]:
        """Queries Grounded programming reference material via Developer Knowledge MCP."""
        res = self._execute_tool_call("query_developer_knowledge", "developer_knowledge", "query_knowledge", {"topic": topic})
        if isinstance(res, list):
            return res
        return [{"excerpt": str(res)}]
