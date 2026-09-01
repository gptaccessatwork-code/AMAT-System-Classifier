import unittest

from system_type_identifier.models import BuildType
from system_type_identifier.parser import parse_system_number


class SystemNumberParserTests(unittest.TestCase):
    def test_normal_system_number(self):
        parsed = parse_system_number(" c02130-ey2-gp1 ")
        self.assertTrue(parsed.valid)
        self.assertEqual(parsed.normalized, "C02130-EY2-GP1")
        self.assertEqual(parsed.build_type, BuildType.NORMAL)
        self.assertEqual(parsed.base_slot_number, "C02130")

    def test_nso_accepts_one_or_two_sequence_digits(self):
        two_digit = parse_system_number("500678N15-DX-GPB")
        one_digit = parse_system_number("C01340R1-EY3-GP2D")
        self.assertTrue(two_digit.valid)
        self.assertEqual(two_digit.build_type, BuildType.NSO)
        self.assertEqual(two_digit.nso_suffix, "N15")
        self.assertTrue(one_digit.valid)
        self.assertEqual(one_digit.build_type, BuildType.NSO)
        self.assertEqual(one_digit.nso_suffix, "R1")

    def test_nso_rejects_three_sequence_digits(self):
        self.assertFalse(parse_system_number("500678N123-DX-GPB").valid)

    def test_rejects_missing_segments(self):
        self.assertFalse(parse_system_number("-GP").valid)


if __name__ == "__main__":
    unittest.main()
