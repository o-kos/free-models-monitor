import unittest
from unittest.mock import patch

from free_models_monitor import notify


class PostJsonTests(unittest.TestCase):
    def test_failure_returns_false_and_error(self):
        with patch(
            "free_models_monitor.notify.urllib.request.urlopen",
            side_effect=OSError("boom"),
        ):
            ok, err = notify._post_json("https://example.com/hook", {"text": "hi"})
        self.assertFalse(ok)
        self.assertIn("boom", err)


class ChannelTests(unittest.TestCase):
    def test_telegram_missing_env_returns_false(self):
        with patch.dict("os.environ", {}, clear=True):
            ok, err = notify.send_telegram("hi")
        self.assertFalse(ok)
        self.assertIn("TELEGRAM", err)

    def test_telegram_posts_to_bot_api_with_env(self):
        env = {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "123"}
        with patch.dict("os.environ", env, clear=True), patch(
            "free_models_monitor.notify._post_json", return_value=(True, None)
        ) as mock_post:
            ok, err = notify.send_telegram("hi")
        self.assertTrue(ok)
        self.assertIsNone(err)
        url, payload = mock_post.call_args[0]
        self.assertIn("tok", url)
        self.assertEqual(payload["chat_id"], "123")

    def test_discord_missing_env_returns_false(self):
        with patch.dict("os.environ", {}, clear=True):
            ok, _err = notify.send_discord("hi")
        self.assertFalse(ok)

    def test_discord_posts_with_env(self):
        with patch.dict(
            "os.environ", {"DISCORD_WEBHOOK_URL": "https://discord/hook"}, clear=True
        ), patch(
            "free_models_monitor.notify._post_json", return_value=(True, None)
        ) as mock_post:
            ok, _err = notify.send_discord("hi")
        self.assertTrue(ok)
        mock_post.assert_called_once()

    def test_slack_missing_env_returns_false(self):
        with patch.dict("os.environ", {}, clear=True):
            ok, _err = notify.send_slack("hi")
        self.assertFalse(ok)

    def test_slack_posts_with_env(self):
        with patch.dict(
            "os.environ", {"SLACK_WEBHOOK_URL": "https://slack/hook"}, clear=True
        ), patch(
            "free_models_monitor.notify._post_json", return_value=(True, None)
        ) as mock_post:
            ok, _err = notify.send_slack("hi")
        self.assertTrue(ok)
        mock_post.assert_called_once()

    def test_webhook_missing_env_returns_false(self):
        with patch.dict("os.environ", {}, clear=True):
            ok, _err = notify.send_webhook("hi")
        self.assertFalse(ok)

    def test_webhook_posts_with_env(self):
        with patch.dict(
            "os.environ", {"WEBHOOK_URL": "https://example/hook"}, clear=True
        ), patch(
            "free_models_monitor.notify._post_json", return_value=(True, None)
        ) as mock_post:
            ok, _err = notify.send_webhook("hi")
        self.assertTrue(ok)
        mock_post.assert_called_once()


class DispatchTests(unittest.TestCase):
    def test_unknown_channel_returns_false(self):
        ok, err = notify.notify("carrier-pigeon", "hi")
        self.assertFalse(ok)
        self.assertIn("unknown", err)

    def test_dispatches_to_registered_channel(self):
        with patch.dict("os.environ", {}, clear=True):
            ok, err = notify.notify("telegram", "hi")
        self.assertFalse(ok)
        self.assertIn("TELEGRAM", err)


if __name__ == "__main__":
    unittest.main()
