import os
import pytest
from agents.sandbox_manager import DockerSandboxManager

def test_sandbox_manager_initialization():
    """Verifies settings and parameters are parsed from environment correctly."""
    os.environ["ORCHESTRA_DOCKER_SANDBOX"] = "true"
    os.environ["SANDBOX_TIMEOUT"] = "60"
    
    manager = DockerSandboxManager()
    assert manager._enabled is True
    assert manager._image_name == "orchestra-sandbox"
    assert manager._timeout_seconds == 60

@pytest.mark.skipif(
    not DockerSandboxManager().is_enabled(),
    reason="Docker daemon is offline or ORCHESTRA_DOCKER_SANDBOX is not set to true"
)
def test_sandbox_simple_command_execution():
    """Verifies successful isolated container execution and output parsing."""
    manager = DockerSandboxManager()
    files = {"test.py": "print('hello from sandbox')"}
    result = manager.execute("python test.py", files)
    
    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert "hello from sandbox" in result["stdout"]
    assert result["duration_ms"] > 0

@pytest.mark.skipif(
    not DockerSandboxManager().is_enabled(),
    reason="Docker daemon is offline or ORCHESTRA_DOCKER_SANDBOX is not set to true"
)
def test_sandbox_stderr_capture():
    """Verifies that error trace logs and exit codes are returned correctly."""
    manager = DockerSandboxManager()
    files = {"fail.py": "import sys; sys.stderr.write('error occurred'); sys.exit(42)"}
    result = manager.execute("python fail.py", files)
    
    assert result["status"] == "failed"
    assert result["exit_code"] == 42
    assert "error occurred" in result["stderr"]

@pytest.mark.skipif(
    not DockerSandboxManager().is_enabled(),
    reason="Docker daemon is offline or ORCHESTRA_DOCKER_SANDBOX is not set to true"
)
def test_sandbox_timeout_enforcement():
    """Verifies execution subprocess is killed upon exceeding sandbox execution timeout limit."""
    manager = DockerSandboxManager()
    original_timeout = manager._timeout_seconds
    manager._timeout_seconds = 1  # enforce 1-second timeout
    
    files = {"sleep.py": "import time; time.sleep(10)"}
    result = manager.execute("python sleep.py", files)
    
    # Restore timeout
    manager._timeout_seconds = original_timeout
    
    assert result["status"] == "failed"
    assert result["exit_code"] == -1
    assert "timed out" in result["stderr"]

@pytest.mark.skipif(
    not DockerSandboxManager().is_enabled(),
    reason="Docker daemon is offline or ORCHESTRA_DOCKER_SANDBOX is not set to true"
)
def test_sandbox_workspace_isolation():
    """Verifies that the /workspace directory volume is mounted read-only for host security."""
    manager = DockerSandboxManager()
    files = {"write_test.py": "import os; open('readonly_test.txt', 'w')"}
    result = manager.execute("python write_test.py", files)
    
    assert result["status"] == "failed"
    assert "Read-only file system" in result["stderr"] or "Permission denied" in result["stderr"]
