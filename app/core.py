"""Makes the Agent Skill's core module importable: the web app is a UI on top of the skill."""

import sys
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).resolve().parent.parent / "skills" / "fabric-inspection" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.append(str(SKILL_SCRIPTS))

import fabric_core  # noqa: E402

__all__ = ["fabric_core"]
