import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unittest
from datetime import date, timedelta

from review_sprint.quantify import quantify
from review_sprint.schedule import build_schedule, phase_plan, schedule_mode, seed_question_types, validate_schedule
from review_sprint.state import new_state
from review_sprint.subjects import get_profile


def state_for(days):
    state = new_state(
        "示例课", date.today() + timedelta(days=days), subject="math",
        profile=get_profile("math"), days=days, daily_minutes=120, target_score=80,
    )
    state["chapters"] = [{"id": f"CH{i}", "title": f"章{i}"} for i in range(1, 4)]
    state["knowledgePoints"] = [
        {"id": f"K{i}", "title": f"知识点{i}", "chapter": f"CH{i % 3 + 1}", "weight": 1.0}
        for i in range(1, 13)
    ]
    state["papers"] = [{"id": "P1", "year": 2024}]
    state["questions"] = [
        {
            "id": f"Q{i}", "paperId": "P1", "type": f"T{i % 12 + 1}",
            "kind": ["basic", "past", "advanced"][i % 3], "points": 5,
            "stem": f"题{i}", "kpIds": [f"K{i % 12 + 1}"],
        }
        for i in range(80)
    ]
    seed_question_types(state)
    quantify(state, 80, days, 120)
    return state


class DaysTest(unittest.TestCase):
    def test_phase_sum_and_load_for_many_n(self):
        for n in (1, 3, 5, 7, 10, 14, 20, 30, 45):
            with self.subTest(n=n):
                state = state_for(n)
                build_schedule(state, days=n)
                days = state["schedule"]["days"]
                self.assertEqual(len(days), n)
                self.assertEqual(len(state.get("phasePlan", [])), n)
                self.assertEqual(sum(1 for row in phase_plan(n, {k: v for k, v in {"build": 0.4, "reinforce": 0.35, "sprint": 0.25}.items()})), n)
                self.assertEqual(validate_schedule(state), [], f"N={n}: {validate_schedule(state)}")
                for day in days:
                    self.assertLessEqual(abs(day.get("loadDeviation", 0)), 0.15 + 1e-9, day)

    def test_phases_are_not_fixed_20(self):
        rows = phase_plan(7, {"build": 0.30, "reinforce": 0.35, "sprint": 0.35})
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["phase"], "诊断期")
        self.assertTrue(any(row["phase"] == "冲刺期" for row in rows))
        self.assertEqual(schedule_mode(3), "emergency")
        self.assertEqual(schedule_mode(5), "compressed")
        self.assertEqual(schedule_mode(12), "standard")
        self.assertEqual(schedule_mode(45), "long")
        long_rows = phase_plan(45, {"build": 0.40, "reinforce": 0.35, "sprint": 0.25})
        self.assertTrue(any("第二轮" in row["phase"] for row in long_rows))


if __name__ == "__main__":
    unittest.main()
