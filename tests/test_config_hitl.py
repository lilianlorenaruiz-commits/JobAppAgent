"""Tests para config.py — valores críticos de HITL."""
import config


class TestHitlTimeout:
    def test_hitl_timeout_at_least_600_seconds(self):
        """10 minutos mínimo — LinkedIn Easy Apply navega ~3 min,
        Lorena necesita tiempo suficiente para revisar y responder SI."""
        assert config.HITL_TIMEOUT_S >= 600, (
            f"HITL_TIMEOUT_S debe ser >= 600 (10 min), fue {config.HITL_TIMEOUT_S}"
        )

    def test_hitl_timeout_exact_value(self):
        """Valor confirmado en 600 por BUG-003 fix."""
        assert config.HITL_TIMEOUT_S == 600
