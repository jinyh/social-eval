from pathlib import Path

from src.knowledge.registry import (
    DEFAULT_FRAMEWORK_ROLE,
    load_scoring_protocol,
    resolve_framework_path,
)


def test_registry_resolves_active_default_framework():
    path = resolve_framework_path(DEFAULT_FRAMEWORK_ROLE)

    assert path.name == "law-v2.56.6-20260522.yaml"
    assert path.is_file()


def test_registry_loads_canonical_ccb_protocol():
    protocol = load_scoring_protocol()

    assert protocol["mode"] == "core_ceiling_bonus"
    assert protocol["total_max"] == 100
    assert Path(protocol["source_path"]).name == "core-ceiling-bonus-v0.8.yaml"
