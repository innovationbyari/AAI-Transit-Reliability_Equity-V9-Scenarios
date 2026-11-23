"""Agentic AI for Public Transit Reliability and Equity: runtime loader for the v9 notebook's engine.

The notebook keeps every section in one shared namespace (later cells use names defined by earlier ones), so `load()`
executes each generated module, in notebook order, inside a single module object: ``transit_ai.runtime``.

    from transit_ai import load
    rt = load()            # runs SETUP 3 → E1 → CV → A → E2 → C → D → governance → E3 → B → E4
    case = rt.APP.new_case(rt.make_raw(rt.PRESETS[name], name))
"""
from __future__ import annotations

import builtins
import json
import os
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES: list[str] = json.loads((HERE / "_modules.json").read_text(encoding="utf-8"))


def param(name, default):
    """Notebook form fields (#@param) become environment-variable overrides, cast to the default's type."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    if isinstance(default, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


_RUNTIME: types.ModuleType | None = None


def load(verbose: bool = False) -> types.ModuleType:
    """Run all section modules once and return the shared runtime module."""
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME
    import matplotlib
    matplotlib.use("Agg")            # no display on a server

    rt = types.ModuleType("transit_ai.runtime")
    rt.__file__ = str(HERE / "__init__.py")
    sys.modules[rt.__name__] = rt    # pydantic / dataclasses resolve annotations through sys.modules
    ns = rt.__dict__
    ns["param"] = param
    ns["USE_OLLAMA"] = param("USE_OLLAMA", False)   # SETUP 2 (Ollama inside Colab) is not part of the web app
    ns["OLLAMA_MODEL"] = param("OLLAMA_MODEL", "llama3.2:3b")
    ns["display"] = lambda *a, **k: None            # notebook display() calls do nothing on the server
    quiet_print = builtins.print if verbose else (lambda *a, **k: None)
    ns["print"] = quiet_print                       # the notebook's progress prints go nowhere unless verbose
    for name in MODULES:
        path = HERE / f"{name}.py"
        code = path.read_text(encoding="utf-8")
        # the notebook imports display/HTML from IPython; keep our no-op display after those imports
        exec(compile(code, str(path), "exec"), ns)
        ns["display"] = lambda *a, **k: None
    _RUNTIME = rt
    return rt
