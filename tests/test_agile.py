import unittest

from system_type_identifier.agile import AgileBomClient, AgileConnectionError


class AgileClientTests(unittest.TestCase):
    def test_requires_username(self):
        with self.assertRaises(AgileConnectionError):
            AgileBomClient("", "password")

    def test_requires_password(self):
        with self.assertRaises(AgileConnectionError):
            AgileBomClient("username", "")


if __name__ == "__main__":
    unittest.main()
