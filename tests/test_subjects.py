import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import unittest
from datetime import date, timedelta

from review_sprint.schedule import _slot_kinds, build_schedule, phase_plan, seed_question_types
from review_sprint.state import new_state
from review_sprint.subjects import (
    REQUIRED_FIELDS, detect_subject, get_profile, num, profile_names, profiles,
)


def _state(subject="math", days=10):
    return new_state(
        "示例课", date.today() + timedelta(days=days), subject=subject,
        profile=get_profile(subject), days=days, daily_minutes=120, target_score=80,
    )


class SubjectProfileTest(unittest.TestCase):
    def test_twelve_plus_general_profiles_load(self):
        names = set(profile_names())
        expected = {
            "cs_systems", "programming", "data_structures", "math", "physics", "circuits",
            "chemistry_biology", "medicine", "law", "economics", "politics",
            "foreign_language", "general",
        }
        self.assertTrue(expected <= names, names)
        self.assertGreaterEqual(len(names), 13)

    def test_required_fields_and_numeric_notes(self):
        def walk(obj, path):
            if isinstance(obj, dict):
                if "value" in obj:
                    self.assertIn("_note", obj, path)
                for key, value in obj.items():
                    walk(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for i, value in enumerate(obj):
                    walk(value, f"{path}[{i}]")

        for name, profile in profiles().items():
            for field in REQUIRED_FIELDS:
                self.assertIn(field, profile, f"{name} missing {field}")
            self.assertTrue(profile["questionTypes"], name)
            for qtype in profile["questionTypes"]:
                self.assertIn("id", qtype)
                self.assertIn("name", qtype)
                self.assertIn("grading", qtype)
                self.assertIn(qtype["grading"], {"auto_exact", "auto_numeric", "rubric", "recite"})
            walk(profile, name)

    def test_mixes_and_phases_are_not_copied(self):
        mixes = []
        phases = []
        for profile in profiles().values():
            mixes.append(tuple(round(num(profile["dailyMix"].get(k)), 2) for k in ("basic", "past", "advanced", "recite")))
            phases.append(tuple(round(num(profile["phaseRatio"].get(k)), 2) for k in ("build", "reinforce", "sprint")))
        self.assertGreater(len(set(mixes)), 1)
        self.assertGreater(len(set(phases)), 1)
        for i in range(len(mixes)):
            self.assertTrue(any(mixes[i] != mixes[j] or phases[i] != phases[j] for j in range(len(mixes)) if i != j))

    def test_detection_math_law_and_low_confidence(self):
        math = detect_subject("极限 导数 积分 矩阵 行列式 概率 期望", "高等数学")
        law = detect_subject("法条 合同 违约责任 侵权 刑法 诉讼 管辖", "法学")
        self.assertEqual(math["subject"], "math")
        self.assertFalse(math["needsConfirmation"])
        self.assertEqual(law["subject"], "law")
        self.assertFalse(law["needsConfirmation"])
        low = detect_subject("考试 复习 重点 知识点", "课程")
        self.assertTrue(low["needsConfirmation"])

    def test_subject_switch_changes_types_mix_and_phases(self):
        results = {}
        for subject in ("math", "law", "politics"):
            state = _state(subject)
            self.assertEqual(state["subject"], subject)
            seed_question_types(state)
            results[subject] = {
                "types": [t["name"] for t in state["questionTypes"]],
                "mix": _slot_kinds(state, 10),
                "phase": tuple(round(num(get_profile(subject)["phaseRatio"].get(k)), 2) for k in ("build", "reinforce", "sprint")),
                "intervals": [num(x["days"]) for x in get_profile(subject)["reviewIntervals"]],
            }
        self.assertNotEqual(results["math"]["types"], results["law"]["types"])
        self.assertNotEqual(results["math"]["mix"], results["law"]["mix"])
        self.assertNotEqual(results["math"]["intervals"], results["politics"]["intervals"])
        self.assertNotEqual(results["law"]["phase"], results["politics"]["phase"])

    def test_no_legacy_csapp_type_constants(self):
        root = Path(__file__).resolve().parents[1] / "scripts" / "review_sprint"
        text = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
        self.assertNotIn("DEFAULT_CSAPP_TYPES", text)
        self.assertNotIn("DEFAULT_GENERIC_TYPES", text)
        self.assertNotIn("4 基础 + 2 真题 + 1 拔高", text)


if __name__ == "__main__":
    unittest.main()
