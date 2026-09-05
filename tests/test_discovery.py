"""Tests for advertised-name matching.

Discovery is the one failure mode with no diagnostic: a hood whose local name
matches nothing simply never appears, and there is nothing in the log to say
why. These tests pin the patterns against both the names we have measured and
the ones we have only inherited.
"""

from __future__ import annotations

import json
from fnmatch import fnmatch
from pathlib import Path

import pytest

from conftest import COMPONENT, const


def matches(name: str) -> bool:
    """Mirror of ``config_flow._name_matches``."""
    return any(fnmatch(name, pattern) for pattern in const.ADVERTISED_NAME_PATTERNS)


@pytest.mark.parametrize(
    "name",
    [
        "Roroshetta Sense",  # what this hood actually advertises
        "Safera Sense",
        "iSense",
        "iSense 2",
        "Sense_1234",
    ],
)
def test_known_names_match(name: str) -> None:
    assert matches(name)


@pytest.mark.parametrize("name", ["", "Sense", "Nonsense", "Some Other Hood"])
def test_unrelated_names_do_not_match(name: str) -> None:
    assert not matches(name)


def test_roroshetta_is_spelled_without_the_slashed_o() -> None:
    """The hood advertises "Roroshetta", not "Røroshetta".

    crillebaba/ha-safera-sense matches ``Røroshetta*``, which would not find
    this hardware at all. Getting this backwards costs discovery entirely, so
    it is asserted in both directions.
    """
    assert matches("Roroshetta Sense")
    assert not fnmatch("Roroshetta Sense", "Røroshetta*")


def test_patterns_agree_with_the_manifest() -> None:
    """Every local_name matcher in the manifest must also match here.

    The manifest drives Home Assistant's discovery and ``const`` drives the
    config flow's own filtering. If they disagree, a hood can be discovered and
    then rejected by the flow it triggered.
    """
    manifest = json.loads((Path(COMPONENT) / "manifest.json").read_text())
    manifest_names = [
        matcher["local_name"]
        for matcher in manifest["bluetooth"]
        if "local_name" in matcher
    ]
    assert manifest_names, "the manifest should carry local_name matchers"
    assert sorted(manifest_names) == sorted(const.ADVERTISED_NAME_PATTERNS)


def test_exact_names_are_a_subset_of_the_patterns() -> None:
    for name in const.ADVERTISED_NAMES:
        assert matches(name)
