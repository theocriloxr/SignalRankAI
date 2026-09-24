import os
import unittest
from unittest.mock import patch

from data import startup_selfcheck


class _FakeResponse:
    ok = True
    status_code = 200

    @staticmethod
    def json():
        return {
            "Information": (
                "We have detected your API key as SUPER_SECRET_ALPHA_KEY "
                "and our standard API rate limit is 25 requests per day."
            )
        }


class TestStartupSelfcheckSecretRedaction(unittest.TestCase):
    def test_alphavantage_throttle_does_not_log_payload_or_api_key(self):
        warnings = []
        with patch.dict(
            os.environ,
            {
                "FX_PAIRS": "EURUSD",
                "ALPHAVANTAGE_API_KEY": "SUPER_SECRET_ALPHA_KEY",
            },
            clear=False,
        ), patch.object(startup_selfcheck.requests, "get", return_value=_FakeResponse()), patch.object(
            startup_selfcheck, "_warn", side_effect=warnings.append
        ):
            ok = startup_selfcheck.check_alphavantage()

        self.assertFalse(ok)
        rendered = "\n".join(warnings)
        self.assertNotIn("SUPER_SECRET_ALPHA_KEY", rendered)
        self.assertNotIn("We have detected your API key", rendered)
        self.assertIn("provider_information_or_rate_limit", rendered)


if __name__ == "__main__":
    unittest.main()
