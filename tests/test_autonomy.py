"""Tests fuer Autonomy Manager."""

from assistant.autonomy import AutonomyManager, ACTION_PERMISSIONS


class TestAutonomyManager:

    def setup_method(self):
        self.manager = AutonomyManager()

    def test_default_level(self):
        assert self.manager.level == 2

    def test_set_valid_level(self):
        assert self.manager.set_level(3) is True
        assert self.manager.level == 3

    def test_set_level_too_low(self):
        assert self.manager.set_level(0) is False
        assert self.manager.level == 2  # unchanged

    def test_set_level_too_high(self):
        assert self.manager.set_level(6) is False
        assert self.manager.level == 2  # unchanged

    def test_can_respond_at_level_1(self):
        self.manager.set_level(1)
        assert self.manager.can_act("respond_to_command") is True

    def test_cannot_proactive_at_level_1(self):
        self.manager.set_level(1)
        assert self.manager.can_act("proactive_info") is False

    def test_can_proactive_at_level_2(self):
        self.manager.set_level(2)
        assert self.manager.can_act("proactive_info") is True

    def test_security_alert_always_allowed(self):
        self.manager.set_level(1)
        assert self.manager.can_act("security_alert") is True

    def test_cannot_create_automation_at_level_4(self):
        self.manager.set_level(4)
        assert self.manager.can_act("create_automation") is False

    def test_can_create_automation_at_level_5(self):
        self.manager.set_level(5)
        assert self.manager.can_act("create_automation") is True

    def test_unknown_action_requires_level_5(self):
        self.manager.set_level(4)
        assert self.manager.can_act("unknown_action") is False
        self.manager.set_level(5)
        assert self.manager.can_act("unknown_action") is True

    def test_get_level_info(self):
        info = self.manager.get_level_info()
        assert info["level"] == 2
        assert info["name"] == "Butler"
        assert "allowed_actions" in info
        assert "respond_to_command" in info["allowed_actions"]
        assert "create_automation" not in info["allowed_actions"]

    def test_level_5_allows_all(self):
        self.manager.set_level(5)
        info = self.manager.get_level_info()
        assert len(info["allowed_actions"]) == len(ACTION_PERMISSIONS)
