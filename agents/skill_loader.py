import os
import yaml
from typing import Dict, Any, Optional
from agents.models import ConfigurationError

class Skill:
    """
    Represents an Antigravity Agent Skill capability containing executable script paths.
    """
    def __init__(self, name: str, version: str, skill_dir: str):
        self.name = name
        self.version = version
        self.skill_dir = skill_dir

    def run(self, *args, **kwargs) -> Any:
        """Executes the skill-specific execution routines."""
        # Simple simulation hook for testing
        return f"Executed skill {self.name} v{self.version} in {self.skill_dir}"

class SkillLoader:
    """
    Resolves skill declarations in the manifest to instantiated Skill wrappers.
    Ensures compatibility boundaries are satisfied.
    """
    def __init__(self, skills_base_dir: Optional[str] = None):
        if not skills_base_dir:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.base_dir = os.path.join(project_root, "skills")
        else:
            self.base_dir = skills_base_dir

    def load_skill(self, name: str, min_version: str = "1.0.0") -> Skill:
        skill_path = os.path.join(self.base_dir, name)
        
        # Verify skill folder existence
        if not os.path.isdir(skill_path):
            raise ConfigurationError(f"Required skill folder '{name}' not found under {self.base_dir}")

        # Check for SKILL.md metadata parsing if present, else fallback
        skill_md_path = os.path.join(skill_path, "SKILL.md")
        version = "1.0.0"
        
        if os.path.isfile(skill_md_path):
            try:
                with open(skill_md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Parse YAML frontmatter if present
                    if content.startswith("---"):
                        parts = content.split("---")
                        if len(parts) >= 3:
                            meta = yaml.safe_load(parts[1])
                            if isinstance(meta, dict):
                                version = str(meta.get("version", "1.0.0"))
            except Exception:
                pass # Fallback to default version
                
        # Basic semver compatibility checks
        # For simplicity, compare major/minor splits
        try:
            curr_parts = [int(p) for p in version.split(".")]
            min_parts = [int(p) for p in min_version.split(".")]
            if curr_parts < min_parts:
                raise ConfigurationError(
                    f"Incompatible version for skill '{name}': "
                    f"Found v{version}, requires at least v{min_version}"
                )
        except ValueError:
            # Non-standard version syntax, fallback to string comparison
            if version < min_version:
                raise ConfigurationError(
                    f"Incompatible version for skill '{name}': "
                    f"Found v{version}, requires at least v{min_version}"
                )

        return Skill(name=name, version=version, skill_dir=skill_path)
