import tempfile
import unittest
from pathlib import Path

from ai_service import AIService
from automation import AutomationEngine
from db import LeadRepository, iso_after


class LeadRescueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = LeadRepository(Path(self.tmp.name) / "test.db")
        self.ai = AIService()
        self.ai.api_key = ""
        self.ai.mode = "demo"

    def tearDown(self):
        self.tmp.cleanup()

    def test_lead_creation_and_quote(self):
        lead = self.repo.create_lead({"name": "Test User", "email": "test@example.com", "service": "Automation"})
        self.assertEqual(lead["status"], "NEW")
        updated = self.repo.set_quote(lead["id"], 500, followup_days=2)
        self.assertEqual(updated["status"], "QUOTE_SENT")
        self.assertEqual(updated["quote_amount"], 500)
        self.assertTrue(updated["next_followup_at"])

    def test_automation_creates_reminder(self):
        lead = self.repo.create_lead({
            "name": "Overdue Lead", "email": "late@example.com", "service": "Quote workflow",
            "status": "QUOTE_SENT", "quote_amount": 750, "next_followup_at": iso_after(hours=-2)
        })
        engine = AutomationEngine(self.repo, self.ai)
        result = engine.run_once()
        self.assertEqual(result["created"], 1)
        reminders = self.repo.list_reminders()
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["lead_id"], lead["id"])
        self.assertIn("Hi", reminders[0]["generated_draft"])

    def test_dashboard_metrics(self):
        self.repo.create_lead({"name": "A", "email": "a@example.com", "status": "NEW"})
        self.repo.create_lead({"name": "B", "email": "b@example.com", "status": "WON", "quote_amount": 900})
        metrics = self.repo.dashboard()
        self.assertEqual(metrics["total_leads"], 2)
        self.assertEqual(metrics["won_value"], 900)


if __name__ == "__main__":
    unittest.main()
