import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unittest
from datetime import date, timedelta

from review_sprint.schedule import (
    build_schedule, due_reviews, next_interval, phase_for, review_kp,
    seed_question_types, validate_schedule,
)
from review_sprint.state import default_settings


def make_state(days=20, types=16, questions=145):
    start = date.today()
    state = {
        "examDate": (start + timedelta(days=days - 1)).isoformat(),
        "dailyMinutes": 120,
        "domain": "cs_systems",
        "settings": default_settings(),
        "chapters": [{"id": f"CH{i}", "title": f"章节{i}"} for i in range(1, 6)],
        "knowledgePoints": [
            {"id": f"K{i}", "title": f"知识点{i}", "chapter": f"CH{i % 5 + 1}"}
            for i in range(1, 31)
        ],
        "questions": [
            {
                "id": f"Q{i}",
                "type": f"T{i % types + 1}",
                "kind": ["basic", "past", "advanced"][i % 3],
                "paperId": f"P{i % 4}",
                "points": 5,
                "stem": f"题目{i}",
            }
            for i in range(questions)
        ],
    }
    seed_question_types(state)
    return state


class ScheduleTest(unittest.TestCase):
    def test_phase_split(self):
        self.assertEqual(phase_for(1, 20), "诊断期")
        self.assertEqual(phase_for(2, 20), "构建期")
        self.assertEqual(phase_for(8, 20), "构建期")
        self.assertEqual(phase_for(9, 20), "强化期")
        self.assertEqual(phase_for(16, 20), "冲刺期")
        self.assertEqual(phase_for(2, 3), "急救期")

    def test_20_day_constraints(self):
        state = make_state()
        build_schedule(state)
        self.assertEqual(validate_schedule(state), [])
        days = state["schedule"]["days"]
        self.assertEqual(len(days), 20)
        self.assertEqual(len([s for s in days[-1]["slots"] if s["kind"] == "mock"]), 10)
        self.assertEqual(len([s for s in days[-1]["slots"] if s["kind"] == "proof"]), 2)
        for tid in [f"T{i}" for i in range(1, 17)]:
            slots = [(d["day"], s) for d in days for s in d["slots"] if s["type"] == tid]
            self.assertGreaterEqual(len(slots), 3, tid)
            self.assertGreaterEqual(len({day for day, _ in slots}), 3, tid)

    def test_load_control(self):
        state = make_state()
        build_schedule(state)
        budget = state["dailyMinutes"]
        extra = state["settings"]["lastDayExtraMinutes"]
        for day in state["schedule"]["days"]:
            allowed = budget + (extra if day["day"] == 20 else 0)
            self.assertLessEqual(day["minutes"], allowed + 5, day["day"])

    def test_reviews_before_exam(self):
        state = make_state()
        build_schedule(state)
        exam = date.fromisoformat(state["examDate"])
        for day in state["schedule"]["days"]:
            for review in day["reviews"]:
                self.assertLess(date.fromisoformat(day["date"]), exam)

    def test_fsrs_update(self):
        state = make_state()
        build_schedule(state)
        kp = state["knowledgePoints"][0]
        result = review_kp(state, kp["id"], 3)
        self.assertEqual(result["kpId"], kp["id"])
        self.assertGreaterEqual(result["stability"], 1.0)
        self.assertTrue(result["due"] <= state["examDate"])

    def test_emergency_mode(self):
        state = make_state(days=3, types=16, questions=30)
        build_schedule(state)
        self.assertTrue(state["schedule"]["emergency"])
        self.assertLessEqual(len(state["schedule"]["coveredTypes"]), 8)
        self.assertEqual(validate_schedule(state), [])

    def test_next_interval(self):
        self.assertAlmostEqual(next_interval(1.0, 0.9), 1.0, places=2)
        self.assertGreater(next_interval(10.0, 0.9), 5.0)

    def test_due_reviews(self):
        state = make_state()
        build_schedule(state)
        state["knowledgePoints"][0]["fsrs"]["due"] = (date.today() - timedelta(days=1)).isoformat()
        due = due_reviews(state)
        self.assertTrue(any(item.get("kpId") == "K1" for item in due))


if __name__ == "__main__":
    unittest.main()
