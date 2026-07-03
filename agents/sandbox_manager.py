import os
import shutil
import tempfile
import time
import subprocess
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("orchestra_sandbox_manager")

class DockerSandboxManager:
    """
    Manages isolated code execution in the Docker-based sandbox container.
    Enforces networking block, memory/CPU bounds, read-only code mounts, and time-caps.
    """
    def __init__(self):
        self._enabled = os.getenv("ORCHESTRA_DOCKER_SANDBOX", "false").lower() == "true"
        self._image_name = "orchestra-sandbox"
        self._timeout_seconds = int(os.getenv("SANDBOX_TIMEOUT", "60"))
        self._memory_limit = os.getenv("SANDBOX_MEMORY", "512m")
        self._cpu_limit = os.getenv("SANDBOX_CPUS", "1")

    def is_enabled(self) -> bool:
        """Checks if containerized execution is enabled and Docker daemon is active."""
        if not self._enabled:
            return False
        try:
            # Perform a fast check to verify Docker daemon connection
            res = subprocess.run(
                ["docker", "info"], 
                capture_output=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                timeout=5
            )
            return res.returncode == 0
        except Exception:
            return False

    def execute(self, command: str, files: Dict[str, str]) -> Dict[str, Any]:
        """
        Runs a shell command inside the dockerized python sandbox.
        Deploys files into a temporary read-only workspace directory mount.
        """
        temp_dir = tempfile.mkdtemp(prefix="orch_sandbox_")
        
        try:
            # Write context files preserving target subdirectory layouts
            for rel_path, content in files.items():
                dest_path = os.path.join(temp_dir, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(content)

            # Normalize temporary path separators for Docker volume binds
            abs_temp_dir = os.path.abspath(temp_dir)
            mount_path = abs_temp_dir.replace("\\", "/")
            
            # Formulate strict sandbox execution arguments
            docker_cmd = [
                "docker", "run", "--rm",
                "--network", "none",
                "--memory", self._memory_limit,
                "--cpus", self._cpu_limit,
                "--pids-limit", "128",
                "-v", f"{mount_path}:/workspace:ro",
                "--tmpfs", "/tmp:rw,noexec,nosuid",
                "-w", "/workspace",
                self._image_name
            ] + command.split()

            logger.info(f"Sandbox execution command: {' '.join(docker_cmd)}")
            
            start_time = time.time()
            try:
                result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    text=True,
                    timeout=self._timeout_seconds
                )
                duration_ms = int((time.time() - start_time) * 1000)
                
                stdout = result.stdout
                stderr = result.stderr
                exit_code = result.returncode
                status = "success" if exit_code == 0 else "failed"
                
            except subprocess.TimeoutExpired as te:
                duration_ms = int((time.time() - start_time) * 1000)
                stdout = te.stdout or ""
                stderr = te.stderr or f"Sandbox execution timed out after {self._timeout_seconds} seconds."
                exit_code = -1
                status = "failed"
                
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "status": status
            }
            
        finally:
            # Clean up ephemeral host mount directory
            shutil.rmtree(temp_dir, ignore_errors=True)
