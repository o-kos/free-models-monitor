import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from free_models_monitor import monitor


class StateDirTests(unittest.TestCase):
    def test_uses_env_var_when_set(self):
        with patch.dict("os.environ", {"FMM_STATE_DIR": "/tmp/custom-fmm"}, clear=True):
            self.assertEqual(monitor.default_state_dir(), "/tmp/custom-fmm")

    def test_falls_back_to_home_dir(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(
                monitor.default_state_dir().endswith(".free-models-monitor")
            )


class JsonHelperTests(unittest.TestCase):
    def test_load_json_safe_returns_default_on_malformed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "broken.json")
            with open(path, "w") as f:
                f.write("{not valid json")
            self.assertEqual(monitor.load_json_safe(path, {"x": 1}), {"x": 1})

    def test_load_fallback_chain_from_list_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "chain.json")
            with open(path, "w") as f:
                json.dump(["openrouter/a:free", "openrouter/b:free"], f)
            self.assertEqual(
                monitor.load_fallback_chain(path),
                ["openrouter/a:free", "openrouter/b:free"],
            )

    def test_load_fallback_chain_from_dict_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "chain.json")
            with open(path, "w") as f:
                json.dump({"fallback_chain": ["openrouter/c:free"]}, f)
            self.assertEqual(monitor.load_fallback_chain(path), ["openrouter/c:free"])

    def test_load_fallback_chain_defaults_without_path(self):
        self.assertEqual(
            monitor.load_fallback_chain(None), list(monitor.DEFAULT_FALLBACK_CHAIN)
        )


class NormalizeTests(unittest.TestCase):
    def test_adds_openrouter_prefix(self):
        self.assertEqual(
            monitor.normalize_model_id("qwen/qwen3-coder:free"),
            "openrouter/qwen/qwen3-coder:free",
        )

    def test_leaves_already_prefixed_alone(self):
        self.assertEqual(
            monitor.normalize_model_id("openrouter/x:free"), "openrouter/x:free"
        )
        self.assertEqual(
            monitor.normalize_model_id("groq/llama-3.3-70b-versatile"),
            "groq/llama-3.3-70b-versatile",
        )

    def test_denormalize_strips_prefix(self):
        self.assertEqual(monitor.denormalize_model_id("openrouter/x:free"), "x:free")
        self.assertEqual(monitor.denormalize_model_id("groq/x"), "groq/x")


class FallbackTests(unittest.TestCase):
    def test_prefers_chain_order_over_context_length(self):
        current = {
            "openrouter/b:free": {"name": "B", "context_length": 999999},
            "openrouter/a:free": {"name": "A", "context_length": 40000},
        }
        chain = ["openrouter/a:free", "openrouter/b:free"]
        model_id, _info = monitor.find_best_fallback(
            current, chain, banned=set(), min_context=32768
        )
        self.assertEqual(model_id, "openrouter/a:free")

    def test_skips_below_min_context(self):
        current = {"openrouter/a:free": {"name": "A", "context_length": 8000}}
        model_id, _info = monitor.find_best_fallback(
            current, ["openrouter/a:free"], banned=set(), min_context=32768
        )
        self.assertIsNone(model_id)

    def test_skips_banned_model(self):
        current = {"openrouter/a:free": {"name": "A", "context_length": 40000}}
        model_id, _info = monitor.find_best_fallback(
            current,
            ["openrouter/a:free"],
            banned={"openrouter/a:free"},
            min_context=32768,
        )
        self.assertIsNone(model_id)

    def test_falls_back_to_highest_context_outside_chain(self):
        current = {
            "openrouter/x:free": {"name": "X", "context_length": 50000},
            "openrouter/y:free": {"name": "Y", "context_length": 90000},
        }
        model_id, _info = monitor.find_best_fallback(
            current, [], banned=set(), min_context=32768
        )
        self.assertEqual(model_id, "openrouter/y:free")

    def test_excludes_removed_model_itself(self):
        current = {"openrouter/a:free": {"name": "A", "context_length": 40000}}
        model_id, _info = monitor.find_best_fallback(
            current,
            ["openrouter/a:free"],
            banned=set(),
            exclude_model="openrouter/a:free",
            min_context=32768,
        )
        self.assertIsNone(model_id)


class HistoryTests(unittest.TestCase):
    def test_caps_at_200_entries(self):
        history = {"changes": []}
        for i in range(250):
            history = monitor.add_history_entry(
                history, "added", f"m{i}", {"name": f"m{i}"}
            )
        self.assertEqual(len(history["changes"]), 200)
        self.assertEqual(history["changes"][-1]["model_id"], "m249")
        self.assertEqual(history["changes"][0]["model_id"], "m50")


class ReportTests(unittest.TestCase):
    def test_text_report_has_no_markdown(self):
        changes = [
            {
                "type": "removed",
                "model_id": "openrouter/a:free",
                "model_info": {"name": "A"},
            }
        ]
        switches = [
            {"from": "openrouter/a:free", "to": "openrouter/b:free", "to_name": "B"}
        ]
        text = monitor.build_report_text(changes, {}, switches, "2026-01-01 00:00 UTC")
        for token in ("**", "##", "```", "__"):
            self.assertNotIn(token, text)
        self.assertIn("openrouter/a:free", text)
        self.assertIn("openrouter/b:free", text)

    def test_text_report_flags_missing_fallback(self):
        changes = [
            {
                "type": "removed",
                "model_id": "openrouter/a:free",
                "model_info": {"name": "A"},
            }
        ]
        switches = [{"from": "openrouter/a:free", "to": None, "to_name": None}]
        text = monitor.build_report_text(changes, {}, switches, "2026-01-01 00:00 UTC")
        self.assertIn("FAILED", text)

    def test_text_report_lists_affected_configs(self):
        changes = [
            {
                "type": "removed",
                "model_id": "openrouter/a:free",
                "model_info": {"name": "A"},
            }
        ]
        affected = {
            "openrouter/a:free": [
                {"file": "/path/to/agent.json", "agent": "agent.json"}
            ]
        }
        text = monitor.build_report_text(changes, affected, [], "2026-01-01 00:00 UTC")
        self.assertIn("/path/to/agent.json", text)

    def test_text_report_added_change(self):
        changes = [
            {
                "type": "added",
                "model_id": "openrouter/new:free",
                "model_info": {"name": "New", "context_length": 50000},
            }
        ]
        text = monitor.build_report_text(changes, {}, [], "2026-01-01 00:00 UTC")
        self.assertIn("ADDED", text)
        self.assertIn("openrouter/new:free", text)
        self.assertIn("ctx=50000", text)


class ScanDirTests(unittest.TestCase):
    def test_finds_affected_agent_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent_dir = os.path.join(tmp, "myagent")
            os.makedirs(agent_dir)
            with open(os.path.join(agent_dir, "config.json"), "w") as f:
                f.write('{"model": "openrouter/a:free"}')
            affected = monitor.find_agents_using_model("openrouter/a:free", [tmp])
            self.assertEqual(len(affected), 1)

    def test_ignores_non_matching_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "notes.txt"), "w") as f:
                f.write("openrouter/a:free")
            affected = monitor.find_agents_using_model("openrouter/a:free", [tmp])
            self.assertEqual(affected, [])


class BanlistTests(unittest.TestCase):
    def test_banned_model_loaded_from_state_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "banned.json"), "w") as f:
                json.dump({"banned_models": ["openrouter/bad:free"]}, f)
            banned = monitor.load_banned_models(tmp)
            self.assertIn("openrouter/bad:free", banned)

    def test_fetch_current_models_filters_banned(self):
        with patch(
            "free_models_monitor.monitor.fetch_openrouter_free"
        ) as mock_or, patch("free_models_monitor.monitor.fetch_groq_free") as mock_groq:
            mock_or.return_value = (
                {
                    "a:free": {"name": "A", "context_length": 1000},
                    "bad:free": {"name": "Bad", "context_length": 1000},
                },
                None,
            )
            mock_groq.return_value = (
                {"groq/g:free": {"name": "G", "context_length": 1000}},
                None,
            )
            current, _counts, errors, quality_context = monitor.fetch_current_models(
                {"openrouter", "groq"}, banned={"openrouter/bad:free"}
            )
            self.assertIn("openrouter/a:free", current)
            self.assertNotIn("openrouter/bad:free", current)
            self.assertIn("groq/g:free", current)
            self.assertEqual(errors, [])
            self.assertIsNone(quality_context)

    def test_fetch_current_models_collects_groq_error(self):
        with patch(
            "free_models_monitor.monitor.fetch_openrouter_free"
        ) as mock_or, patch("free_models_monitor.monitor.fetch_groq_free") as mock_groq:
            mock_or.return_value = (
                {"a:free": {"name": "A", "context_length": 1000}},
                None,
            )
            mock_groq.return_value = (None, "Groq fetch error: boom")
            current, _counts, errors, quality_context = monitor.fetch_current_models(
                {"openrouter", "groq"}, banned=set()
            )
            self.assertIn("openrouter/a:free", current)
            self.assertEqual(errors, ["Groq fetch error: boom"])
            self.assertIsNone(quality_context)


class QualityChangeTests(unittest.TestCase):
    def quality_info(self, status, coding=72, agentic=48):
        return {
            "name": "Model",
            "context_length": 200000,
            "coding_index": coding,
            "agentic_index": agentic,
            "quality": {
                "status": status,
                "coding_ratio": coding / 80 if coding is not None else None,
                "agentic_ratio": agentic / 60 if agentic is not None else None,
            },
        }

    def test_frontier_mode_filters_new_weak_model(self):
        current = {
            "openrouter/weak:free": self.quality_info(
                "below_threshold", coding=40, agentic=20
            )
        }
        changes, _affected, _switches, _history = monitor.compute_diff(
            current,
            {},
            [],
            [],
            set(),
            32768,
            {"changes": []},
            quality_mode="frontier",
        )
        self.assertEqual(changes, [])

    def test_candidate_mode_reports_new_unscored_model(self):
        current = {
            "openrouter/new:free": self.quality_info(
                "candidate", coding=None, agentic=None
            )
        }
        changes, _affected, _switches, _history = monitor.compute_diff(
            current,
            {},
            [],
            [],
            set(),
            32768,
            {"changes": []},
            quality_mode="candidate",
        )
        self.assertEqual(changes[0]["type"], "quality_candidate")

    def test_existing_candidate_promotion_is_reported(self):
        model_id = "openrouter/promoted:free"
        current = {model_id: self.quality_info("confirmed")}
        snapshot = {
            model_id: self.quality_info("candidate", coding=None, agentic=None)
        }
        changes, _affected, _switches, history = monitor.compute_diff(
            current,
            snapshot,
            [],
            [],
            set(),
            32768,
            {"changes": []},
            quality_mode="frontier",
        )
        self.assertEqual(changes[0]["type"], "quality_confirmed")
        self.assertEqual(history["changes"][0]["type"], "quality_confirmed")

    def test_text_report_includes_quality_scores(self):
        info = self.quality_info("confirmed")
        text = monitor.build_report_text(
            [
                {
                    "type": "quality_confirmed",
                    "model_id": "openrouter/good:free",
                    "model_info": info,
                }
            ],
            {},
            [],
            "2026-01-01 00:00 UTC",
        )
        self.assertIn("paid-frontier", text)
        self.assertIn("90.0%", text)

    def test_quality_filter_keeps_groq_additions(self):
        info = {"name": "Groq model", "context_length": 128000}
        self.assertEqual(
            monitor.quality_change_type("groq/model", info, "frontier"), "added"
        )

    def test_fetch_current_models_applies_live_frontier(self):
        def catalog_model(model_id, prompt, coding, agentic):
            return {
                "id": model_id,
                "name": model_id,
                "pricing": {"prompt": prompt, "completion": prompt},
                "context_length": 200000,
                "architecture": {"output_modalities": ["text"]},
                "supported_parameters": ["tools"],
                "benchmarks": {
                    "artificial_analysis": {
                        "coding_index": coding,
                        "agentic_index": agentic,
                    }
                },
            }

        catalog = [
            catalog_model("paid/frontier", "0.1", 80, 60),
            catalog_model("free/good:free", "0", 72, 48),
        ]
        config = {"coding_ratio": 0.9, "agentic_ratio": 0.8, "min_context": 128000}
        with patch(
            "free_models_monitor.monitor.fetch_openrouter_catalog",
            return_value=(catalog, None),
        ):
            current, counts, errors, quality_context = monitor.fetch_current_models(
                {"openrouter"}, banned=set(), quality_config=config
            )
        self.assertEqual(errors, [])
        self.assertEqual(counts["openrouter"], 1)
        self.assertEqual(
            current["openrouter/free/good:free"]["quality"]["status"],
            "confirmed",
        )
        self.assertEqual(quality_context["frontier"]["coding_index"], 80)


class MainExitCodeTests(unittest.TestCase):
    def test_init_returns_zero_and_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "free_models_monitor.monitor.fetch_openrouter_free"
            ) as mock_or, patch(
                "free_models_monitor.monitor.fetch_groq_free"
            ) as mock_groq:
                mock_or.return_value = (
                    {"a:free": {"name": "A", "context_length": 100000}},
                    None,
                )
                mock_groq.return_value = ({}, None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = monitor.main(["--state-dir", tmp, "--init"])
                self.assertEqual(code, 0)
                self.assertTrue(os.path.exists(os.path.join(tmp, "snapshot.json")))

    def test_removed_model_returns_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {"openrouter/a:free": {"name": "A", "context_length": 100000}}
            with open(os.path.join(tmp, "snapshot.json"), "w") as f:
                json.dump(snapshot, f)
            with patch(
                "free_models_monitor.monitor.fetch_openrouter_free"
            ) as mock_or, patch(
                "free_models_monitor.monitor.fetch_groq_free"
            ) as mock_groq:
                mock_or.return_value = ({}, None)
                mock_groq.return_value = ({}, None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = monitor.main(["--state-dir", tmp, "--format", "text"])
                self.assertEqual(code, 2)
                self.assertIn("REMOVED", buf.getvalue())

    def test_no_changes_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {"openrouter/a:free": {"name": "A", "context_length": 100000}}
            with open(os.path.join(tmp, "snapshot.json"), "w") as f:
                json.dump(snapshot, f)
            with patch(
                "free_models_monitor.monitor.fetch_openrouter_free"
            ) as mock_or, patch(
                "free_models_monitor.monitor.fetch_groq_free"
            ) as mock_groq:
                mock_or.return_value = (
                    {"a:free": {"name": "A", "context_length": 100000}},
                    None,
                )
                mock_groq.return_value = ({}, None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = monitor.main(["--state-dir", tmp])
                self.assertEqual(code, 0)

    def test_all_providers_failing_returns_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("free_models_monitor.monitor.fetch_openrouter_free") as mock_or:
                mock_or.return_value = (None, "boom")
                code = monitor.main(["--state-dir", tmp, "--providers", "openrouter"])
                self.assertEqual(code, 1)

    def test_quality_failure_returns_one_without_overwriting_state(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "free_models_monitor.monitor.fetch_current_models",
            return_value=(
                {"openrouter/a:free": {"name": "A"}},
                {"openrouter": 1},
                ["quality unavailable"],
                {"available": False, "error": "quality unavailable"},
            ),
        ):
            code = monitor.main(
                ["--state-dir", tmp, "--quality-filter", "frontier"]
            )
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(os.path.join(tmp, "snapshot.json")))

    def test_scan_dir_reports_affected_config_on_removal(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as scan_dir:
            snapshot = {"openrouter/a:free": {"name": "A", "context_length": 100000}}
            with open(os.path.join(tmp, "snapshot.json"), "w") as f:
                json.dump(snapshot, f)
            with open(os.path.join(scan_dir, "agent.json"), "w") as f:
                f.write('{"model": "openrouter/a:free"}')
            with patch(
                "free_models_monitor.monitor.fetch_openrouter_free"
            ) as mock_or, patch(
                "free_models_monitor.monitor.fetch_groq_free"
            ) as mock_groq:
                mock_or.return_value = ({}, None)
                mock_groq.return_value = ({}, None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = monitor.main(
                        ["--state-dir", tmp, "--scan-dir", scan_dir, "--format", "json"]
                    )
                self.assertEqual(code, 2)
                report = json.loads(buf.getvalue())
                self.assertEqual(
                    len(report["affected_configs"]["openrouter/a:free"]), 1
                )

    def test_removed_model_with_fallback_suggests_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {
                "openrouter/a:free": {"name": "A", "context_length": 100000},
                "openrouter/b:free": {"name": "B", "context_length": 100000},
            }
            with open(os.path.join(tmp, "snapshot.json"), "w") as f:
                json.dump(snapshot, f)
            with patch(
                "free_models_monitor.monitor.fetch_openrouter_free"
            ) as mock_or, patch(
                "free_models_monitor.monitor.fetch_groq_free"
            ) as mock_groq:
                mock_or.return_value = (
                    {"b:free": {"name": "B", "context_length": 100000}},
                    None,
                )
                mock_groq.return_value = ({}, None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = monitor.main(["--state-dir", tmp, "--format", "json"])
                self.assertEqual(code, 2)
                report = json.loads(buf.getvalue())
                switch = report["switches"][0]
                self.assertEqual(switch["from"], "openrouter/a:free")
                self.assertEqual(switch["to"], "openrouter/b:free")
                history = monitor.load_json_safe(os.path.join(tmp, "history.json"), {})
                types = [c["type"] for c in history["changes"]]
                self.assertIn("switch_suggested", types)

    def test_notify_called_when_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {"openrouter/a:free": {"name": "A", "context_length": 100000}}
            with open(os.path.join(tmp, "snapshot.json"), "w") as f:
                json.dump(snapshot, f)
            with patch(
                "free_models_monitor.monitor.fetch_openrouter_free"
            ) as mock_or, patch(
                "free_models_monitor.monitor.fetch_groq_free"
            ) as mock_groq, patch(
                "free_models_monitor.monitor.notify_mod.notify",
                return_value=(True, None),
            ) as mock_notify:
                mock_or.return_value = ({}, None)
                mock_groq.return_value = ({}, None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = monitor.main(["--state-dir", tmp, "--notify", "webhook"])
                self.assertEqual(code, 2)
                mock_notify.assert_called_once()
                self.assertEqual(mock_notify.call_args[0][0], "webhook")

    def test_notify_failure_prints_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {"openrouter/a:free": {"name": "A", "context_length": 100000}}
            with open(os.path.join(tmp, "snapshot.json"), "w") as f:
                json.dump(snapshot, f)
            with patch(
                "free_models_monitor.monitor.fetch_openrouter_free"
            ) as mock_or, patch(
                "free_models_monitor.monitor.fetch_groq_free"
            ) as mock_groq, patch(
                "free_models_monitor.monitor.notify_mod.notify",
                return_value=(False, "boom"),
            ):
                mock_or.return_value = ({}, None)
                mock_groq.return_value = ({}, None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = monitor.main(["--state-dir", tmp, "--notify", "webhook"])
                self.assertEqual(code, 2)

    def test_notify_always_fires_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = {"openrouter/a:free": {"name": "A", "context_length": 100000}}
            with open(os.path.join(tmp, "snapshot.json"), "w") as f:
                json.dump(snapshot, f)
            with patch(
                "free_models_monitor.monitor.fetch_openrouter_free"
            ) as mock_or, patch(
                "free_models_monitor.monitor.fetch_groq_free"
            ) as mock_groq, patch(
                "free_models_monitor.monitor.notify_mod.notify",
                return_value=(True, None),
            ) as mock_notify:
                mock_or.return_value = (
                    {"a:free": {"name": "A", "context_length": 100000}},
                    None,
                )
                mock_groq.return_value = ({}, None)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = monitor.main(
                        ["--state-dir", tmp, "--notify", "webhook", "--notify-always"]
                    )
                self.assertEqual(code, 0)
                mock_notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
