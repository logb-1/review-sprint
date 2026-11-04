import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unittest
from datetime import date, timedelta

from review_sprint.answer_check import compare, compute
from review_sprint.quantify import quantify
from review_sprint.schedule import seed_question_types
from review_sprint.state import new_state
from review_sprint.subjects import get_profile


def make_state(subject="math", days=10, target=80):
    state = new_state(
        "示例课", date.today() + timedelta(days=days), subject=subject,
        profile=get_profile(subject), days=days, daily_minutes=120, target_score=target,
    )
    state["chapters"] = [{"id": f"CH{i}", "title": f"章{i}"} for i in range(1, 4)]
    state["knowledgePoints"] = [
        {"id": f"K{i}", "title": f"知识点{i}", "chapter": f"CH{i % 3 + 1}", "weight": 1.0}
        for i in range(1, 13)
    ]
    state["papers"] = [
        {"id": "P1", "year": 2023, "sameAs": None},
        {"id": "P2", "year": 2024, "sameAs": None},
    ]
    state["questions"] = []
    for i in range(36):
        state["questions"].append({
            "id": f"P{i % 2 + 1}-Q{i + 1}",
            "paperId": f"P{i % 2 + 1}",
            "type": f"T{i % 12 + 1}",
            "kind": ["basic", "past", "advanced"][i % 3],
            "points": 5 + (i % 3) * 2,
            "stem": f"题目{i}",
            "kpIds": [f"K{i % 12 + 1}"],
        })
    seed_question_types(state)
    return state


class QuantifyTest(unittest.TestCase):
    def test_higher_target_needs_more(self):
        state = make_state()
        low = quantify(state, 60, 10, 120)
        low_minutes = low["totalMinutes"]
        low_questions = low["practiceQuestions"]
        high = quantify(state, 90, 10, 120)
        self.assertGreaterEqual(high["totalMinutes"], low_minutes)
        self.assertGreaterEqual(high["practiceQuestions"], low_questions)
        self.assertGreaterEqual(len(high["levels"]), len(low["levels"]))
        self.assertEqual({row["target"] for row in high["matrix"]}, {60, 70, 80, 90, 95})
        self.assertTrue(any(row["selected"] for row in high["matrix"] if row["target"] == 90))

    def test_over_capacity_reports_reachable_and_abandoned(self):
        state = make_state(days=1)
        result = quantify(state, 95, 1, 20)
        self.assertLessEqual(result["reachableScore"], 100)
        self.assertGreaterEqual(result["shortfall"], 0)
        self.assertIsInstance(result["abandoned"], list)
        if result["shortfall"] > 0:
            self.assertTrue(result["abandoned"])

    def test_mastery_targets_are_written(self):
        state = make_state()
        quantify(state, 80, 10, 120)
        self.assertTrue(state["mastery"])
        self.assertTrue(any(v.get("targetLevel") in {"L0", "L1", "L2", "L3", "L4"} for v in state["mastery"].values()))
        self.assertTrue(all("targetLevel" in v for v in state["mastery"].values()))

    def test_matrix_determinant_checkers(self):
        result = compute({"kind": "determinant", "rows": [[1, 2], [3, 4]]})
        self.assertAlmostEqual(result["value"], -2.0)
        self.assertEqual(compare("-2", result), "same")
        matrix = compute({"kind": "matrix", "op": "equal", "a": [[1, 2]], "b": [[1, 2]]})
        self.assertTrue(matrix["equal"])


if __name__ == "__main__":
    unittest.main()
