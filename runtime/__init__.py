"""Runtime role boundaries.

The role modules deliberately import application components lazily.  This keeps
the dispatcher cheap to import (and safe for health checks) while allowing the
existing monolith to remain the compatibility implementation during the role
decomposition pass.
"""

from runtime.roles import RunMode, infer_run_mode, parse_run_mode

__all__ = ["RunMode", "infer_run_mode", "parse_run_mode"]
