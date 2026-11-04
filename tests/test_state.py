import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unittest
from datetime import date

from review_sprint.state import add_attempt


class StateTest(unittest.TestCase):
    def test_mistake_closes_after_two_correct_days(self):
        state = {"attempts": [], "mistakes": []}
        add_attempt(state, "Q1", False, confidence=3, cause="concept", on=date(2026, 1, 1))
        self.assertEqual(len(state["mistakes"]), 1)
        add_attempt(state, "Q1", True, confidence=2, on=date(2026, 1, 1))
        self.assertFalse(state["mistakes"][0]["resolved"])
        add_attempt(state, "Q1", True, confidence=2, on=date(2026, 1, 2))
        self.assertTrue(state["mistakes"][0]["resolved"])
        self.assertEqual(state["mistakes"][0]["resolvedAt"], "2026-01-02")

    def test_wrong_attempt_refreshes_existing_mistake(self):
        state = {"attempts": [], "mistakes": []}
        add_attempt(state, "Q1", False, confidence=1, cause="calc", on=date(2026, 1, 1))
        add_attempt(state, "Q1", False, confidence=3, cause="concept", on=date(2026, 1, 3))
        self.assertEqual(len(state["mistakes"]), 1)
        self.assertTrue(state["mistakes"][0]["highConfidence"])
        self.assertEqual(state["mistakes"][0]["retestDue"], "2026-01-04")


if __name__ == "__main__":
    unittest.main()
