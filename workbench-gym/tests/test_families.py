# SPDX-License-Identifier: Apache-2.0

"""Every registered family passes every gate. Set GATE_SEEDS to change the seed count."""

import os

import pytest

from tests.gates import check_family
from workbench_gym.families import FAMILY_MODULES, load_families

SEEDS = int(os.environ.get("GATE_SEEDS", "200"))
FAMILIES = load_families()


def test_every_listed_family_is_registered():
    missing = sorted(set(FAMILY_MODULES) - set(FAMILIES))
    assert not missing, f"families not written yet: {missing}"


@pytest.mark.parametrize("family_id", sorted(FAMILIES))
def test_family_passes_gates(family_id):
    problems = check_family(FAMILIES[family_id], SEEDS)
    assert not problems, "\n".join(problems)
