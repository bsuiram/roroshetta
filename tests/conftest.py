"""Make the integration package importable without Home Assistant installed.

``parser.py`` and ``const.py`` are deliberately free of Home Assistant and bleak
imports, so they can be loaded directly by file path. Importing the package the
normal way would execute ``__init__.py``, which does need Home Assistant.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "safera"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, COMPONENT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


const = _load("const")
parser = _load("parser")
