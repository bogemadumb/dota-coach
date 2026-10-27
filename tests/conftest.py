import pytest


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    def forbidden(options):
        raise AssertionError("test tried to start a real Claude session")

    monkeypatch.setattr("dota_coach.brain.default_client_factory", forbidden)
