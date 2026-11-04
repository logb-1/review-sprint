import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import unittest

from review_sprint.answer_check import (
    alu_flags, compare, compute, decode_bits, hex_bits, ieee754_decode,
    ieee754_encode, machine_code, modrm,
)


class AnswerCheckTest(unittest.TestCase):
    def test_twos_complement(self):
        self.assertEqual(hex_bits(-5, 8), "0xFB")
        self.assertEqual(decode_bits("11111011", signed=True), -5)
        self.assertEqual(decode_bits("11111011", signed=False), 251)

    def test_ieee754(self):
        self.assertEqual(ieee754_encode(-6.5, 32), "0xC0D00000")
        self.assertAlmostEqual(ieee754_decode("0xC0D00000", 32), -6.5)
        self.assertAlmostEqual(ieee754_decode(ieee754_encode(3.14, 64), 64), 3.14)

    def test_flags_sub(self):
        flags = alu_flags(5, 7, "sub", 8)
        self.assertEqual(flags["CF"], 1)
        self.assertEqual(flags["SF"], 1)
        self.assertEqual(flags["ZF"], 0)
        self.assertEqual(flags["OF"], 0)
        self.assertEqual(flags["resultHex"], "0xFE")

    def test_flags_overflow(self):
        flags = alu_flags(0x7F, 1, "add", 8)
        self.assertEqual(flags["OF"], 1)
        self.assertEqual(flags["SF"], 1)
        self.assertEqual(flags["resultHex"], "0x80")

    def test_flags_carry_zero(self):
        flags = alu_flags(0xFF, 1, "add", 8)
        self.assertEqual(flags["CF"], 1)
        self.assertEqual(flags["ZF"], 1)
        self.assertEqual(flags["OF"], 0)

    def test_modrm(self):
        self.assertEqual(modrm(1, 0, 4), 0x44)
        self.assertEqual(compute({"kind": "modrm", "mod": 1, "reg": 0, "rm": 4})["byte"], "0x44")

    def test_machine_code(self):
        self.assertEqual(machine_code("mov", ["rax", "rbx"]), "4889D8")
        self.assertEqual(machine_code("lea", ["rax", ("rbx", 8)]), "488D4308")
        self.assertEqual(machine_code("mov", [("rbx", 8), "rax"]), "48894308")
        self.assertEqual(machine_code("ret", []), "C3")
        self.assertEqual(machine_code("jmp", [2]), "EB02")

    def test_compute_and_compare(self):
        result = compute({"kind": "twos", "value": -5, "bits": 8})
        self.assertEqual(result["hex"], "0xFB")
        self.assertEqual(compare("0xFB", result), "same")
        self.assertEqual(compare("251", result), "same")
        self.assertEqual(compare("FB", result), "same")
        self.assertEqual(compare("0xFA", result), "different")

    def test_compare_flags(self):
        result = compute({"kind": "flags", "op": "sub", "a": 5, "b": 7, "bits": 8})
        self.assertEqual(compare("CF=1, SF=1", result), "same")
        self.assertEqual(compare("CF=0", result), "different")

    def test_generic_checkers(self):
        choice = compute({"kind": "choice", "answer": "AB"})
        self.assertEqual(compare("B,A", choice), "same")
        self.assertEqual(compare("A", choice), "different")
        numeric = compute({"kind": "numeric", "value": 3.14, "tolerance": 0.01})
        self.assertEqual(compare("3.145", numeric), "same")
        self.assertEqual(compare("3.2", numeric), "different")
        exact = compute({"kind": "exact", "text": "违约责任"})
        self.assertEqual(compare("违约责任", exact), "same")


if __name__ == "__main__":
    unittest.main()

