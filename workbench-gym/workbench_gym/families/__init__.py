# SPDX-License-Identifier: Apache-2.0

"""
Family registry. Each module named here defines ``FAMILY``, an instance of Family.

A module that is still missing is skipped, so the registry loads while families
are being written. The gates test that every listed family exists.
"""

import importlib

from .base import Family

FAMILY_MODULES = [
    "sw1",
    "sw2",
    "sw3",
    "ind1",
    "ind2",
    "ind3",
    "sci1",
    "sci2",
    "sci3",
    "off1",
    "off2",
    "off3",
    "fin1",
    "fin2",
    "fin3",
    "math1",
    "math2",
    "math3",
    "sec1",
    "sec2",
    "sec3",
    "med1",
    "med2",
    "med3",
]

DOMAIN_IDS = {
    "software-engineering",
    "industrial-physical-systems",
    "natural-science",
    "office-white-collar",
    "finance-economics",
    "mathematics-or-formal-reasoning",
    "cybersecurity",
    "media-content-production",
}


def load_families() -> dict[str, Family]:
    families: dict[str, Family] = {}
    for name in FAMILY_MODULES:
        try:
            module = importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as exc:
            if exc.name == f"{__name__}.{name}":
                continue
            raise
        family = module.FAMILY
        if family.id != name:
            raise ValueError(f"module {name} defines family {family.id}")
        families[family.id] = family
    return families
