import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from free_models_monitor import providers


class FreePriceTests(unittest.TestCase):
    def test_recognizes_various_zero_representations(self):
        for value in ("0", "0.0", 0, 0.0):
            self.assertTrue(providers._is_free_price(value))

    def test_rejects_nonzero_and_invalid(self):
        self.assertFalse(providers._is_free_price("0.001"))
        self.assertFalse(providers._is_free_price(None))
        self.assertFalse(providers._is_free_price("not-a-number"))


class FetchOpenRouterTests(unittest.TestCase):
    def test_keeps_only_zero_priced_models(self):
        payload = {
            "data": [
                {
                    "id": "a:free",
                    "name": "A",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "context_length": 1000,
                },
                {
                    "id": "b:paid",
                    "name": "B",
                    "pricing": {"prompt": "0.002", "completion": "0"},
                    "context_length": 1000,
                },
            ]
        }
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.__enter__.return_value = mock_resp
        with patch(
            "free_models_monitor.providers.urllib.request.urlopen",
            return_value=mock_resp,
        ):
            free, err = providers.fetch_openrouter_free()
        self.assertIsNone(err)
        self.assertIn("a:free", free)
        self.assertNotIn("b:paid", free)

    def test_network_error_returns_none_and_message(self):
        with patch(
            "free_models_monitor.providers.urllib.request.urlopen",
            side_effect=urllib.error.URLError("boom"),
        ), patch("free_models_monitor.providers.time.sleep"):
            free, err = providers.fetch_openrouter_free()
        self.assertIsNone(free)
        self.assertIn("OpenRouter fetch error", err)

    def test_malformed_json_returns_none_and_message(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__.return_value = mock_resp
        with patch(
            "free_models_monitor.providers.urllib.request.urlopen",
            return_value=mock_resp,
        ), patch("free_models_monitor.providers.time.sleep"):
            free, err = providers.fetch_openrouter_free()
        self.assertIsNone(free)
        self.assertIn("OpenRouter fetch error", err)

    def test_preserves_quality_metadata_for_free_models(self):
        catalog = [
            {
                "id": "coder:free",
                "name": "Coder",
                "pricing": {"prompt": "0", "completion": "0"},
                "context_length": 200000,
                "supported_parameters": ["tools"],
                "benchmarks": {
                    "artificial_analysis": {
                        "coding_index": 72,
                        "agentic_index": 48,
                    }
                },
            }
        ]
        free = providers.openrouter_free_from_catalog(catalog)
        self.assertTrue(free["coder:free"]["supports_tools"])
        self.assertEqual(free["coder:free"]["coding_index"], 72)
        self.assertEqual(free["coder:free"]["agentic_index"], 48)


class FetchGroqTests(unittest.TestCase):
    def test_returns_static_list_copy(self):
        free, err = providers.fetch_groq_free()
        self.assertIsNone(err)
        self.assertEqual(free, providers.GROQ_FREE_MODELS)
        self.assertIsNot(free, providers.GROQ_FREE_MODELS)


class RegistryTests(unittest.TestCase):
    def test_providers_registry_has_both_entries(self):
        self.assertEqual(set(providers.PROVIDERS), {"openrouter", "groq"})


if __name__ == "__main__":
    unittest.main()
