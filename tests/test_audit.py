"""Tests fuer Audit Logger."""

from assistant.audit import AuditLogger


class TestAuditLogger:

    def setup_method(self):
        self.audit = AuditLogger(max_entries=10)

    def test_log_action(self):
        self.audit.log_action("set_light", {"room": "wohnzimmer"}, {"success": True, "message": "OK"})
        entries = self.audit.get_recent(10)
        assert len(entries) == 1
        assert entries[0]["function"] == "set_light"
        assert entries[0]["success"] is True

    def test_log_with_person(self):
        self.audit.log_action("set_light", {}, {"success": True}, person="Max")
        entries = self.audit.get_recent()
        assert entries[0]["person"] == "Max"

    def test_log_with_request_id(self):
        self.audit.log_action("set_light", {}, {"success": True}, request_id="abc123")
        entries = self.audit.get_recent()
        assert entries[0]["request_id"] == "abc123"

    def test_max_entries_enforced(self):
        for i in range(15):
            self.audit.log_action(f"func_{i}", {}, {"success": True})
        entries = self.audit.get_recent(20)
        assert len(entries) == 10

    def test_get_recent_order(self):
        self.audit.log_action("first", {}, {"success": True})
        self.audit.log_action("second", {}, {"success": True})
        entries = self.audit.get_recent()
        assert entries[0]["function"] == "second"  # Neueste zuerst
        assert entries[1]["function"] == "first"

    def test_get_by_person(self):
        self.audit.log_action("func1", {}, {"success": True}, person="Max")
        self.audit.log_action("func2", {}, {"success": True}, person="Lisa")
        self.audit.log_action("func3", {}, {"success": True}, person="Max")

        max_entries = self.audit.get_by_person("Max")
        assert len(max_entries) == 2
        assert all(e["person"] == "Max" for e in max_entries)

    def test_empty_log(self):
        assert self.audit.get_recent() == []
        assert self.audit.get_by_person("Max") == []

    def test_failed_action(self):
        self.audit.log_action("set_light", {"room": "x"}, {"success": False, "message": "Nicht gefunden"})
        entries = self.audit.get_recent()
        assert entries[0]["success"] is False
