import json
from pathlib import Path
import unittest
from uuid import uuid4

from system_type_identifier.agile import AgileConnectionError, load_script_credentials


class AgileCredentialTests(unittest.TestCase):
    def scratch_path(self) -> Path:
        path = Path.cwd() / f"test_{uuid4().hex}_credentials.json"
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_loads_agile_keys_from_shared_format(self):
        path = self.scratch_path()
        path.write_text(
            json.dumps({"AGILE_USER": "test-user", "AGILE_PASS": "test-pass"}),
            encoding="utf-8",
        )
        credentials = load_script_credentials(path)
        self.assertEqual(credentials.username, "test-user")
        self.assertEqual(credentials.password, "test-pass")

    def test_rejects_missing_agile_keys(self):
        path = self.scratch_path()
        path.write_text(json.dumps({"ORACLE_USER": "unused"}), encoding="utf-8")
        with self.assertRaises(AgileConnectionError):
            load_script_credentials(path)


if __name__ == "__main__":
    unittest.main()
