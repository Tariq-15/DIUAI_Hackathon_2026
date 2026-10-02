"""Shared fixtures. A small world (fast) is built once per test session."""

from __future__ import annotations

import pytest

from ferot.datagen.complaints import attach_complaints
from ferot.datagen.generator import build_world


@pytest.fixture(scope="session")
def small_world():
    world = build_world(seed=7, customers=600, days=90)
    world.cases = attach_complaints(world.cases, 7)
    return world
