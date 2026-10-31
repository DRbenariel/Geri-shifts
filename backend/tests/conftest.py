import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.dirname(__file__))

from fixtures import build  # noqa: E402
from geri_core import DataContext, MemoryStore  # noqa: E402


class RecMailer:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))


@pytest.fixture
def frames():
    return build()


@pytest.fixture
def ctx(frames):
    store = MemoryStore(frames)
    return DataContext.load(store, mailer=RecMailer())


@pytest.fixture
def legacy(ctx):
    from legacy import load_legacy, seed_session
    ns, st, io = load_legacy()
    seed_session(ns, st, io, ctx)
    return ns, st, io
