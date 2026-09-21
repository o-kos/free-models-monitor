import unittest

from free_models_monitor import quality


def model(
    model_id,
    prompt,
    completion,
    coding=None,
    agentic=None,
    context=200000,
    tools=True,
):
    parameters = ["tools"] if tools else []
    return {
        "id": model_id,
        "name": model_id,
        "pricing": {"prompt": prompt, "completion": completion},
        "context_length": context,
        "architecture": {"output_modalities": ["text"]},
        "supported_parameters": parameters,
        "benchmarks": {
            "artificial_analysis": {
                "coding_index": coding,
                "agentic_index": agentic,
            }
        },
    }


class FrontierTests(unittest.TestCase):
    def test_uses_best_paid_scores_and_ignores_free_models(self):
        catalog = [
            model("paid/a", "0.1", "0.2", coding=80, agentic=40),
            model("paid/b", "0.1", "0.2", coding=70, agentic=60),
            model("free/x:free", "0", "0", coding=99, agentic=99),
        ]
        frontier = quality.build_paid_frontier(catalog)
        self.assertEqual(frontier["coding_index"], 80)
        self.assertEqual(frontier["coding_model"], "paid/a")
        self.assertEqual(frontier["agentic_index"], 60)
        self.assertEqual(frontier["agentic_model"], "paid/b")

    def test_requires_both_benchmark_families(self):
        with self.assertRaises(ValueError):
            quality.build_paid_frontier(
                [model("paid/a", "0.1", "0.2", coding=80, agentic=None)]
            )


class ClassificationTests(unittest.TestCase):
    frontier = {"coding_index": 80, "agentic_index": 60}

    def info(self, coding=None, agentic=None, context=200000, tools=True):
        return {
            "name": "Free",
            "context_length": context,
            "supports_tools": tools,
            "supports_text": True,
            "is_router": False,
            "coding_index": coding,
            "agentic_index": agentic,
        }

    def test_confirms_model_near_both_paid_frontiers(self):
        result = quality.classify(self.info(coding=72, agentic=48), self.frontier)
        self.assertEqual(result["quality"]["status"], "confirmed")
        self.assertEqual(result["quality"]["coding_ratio"], 0.9)
        self.assertEqual(result["quality"]["agentic_ratio"], 0.8)

    def test_marks_capable_unscored_model_as_candidate(self):
        result = quality.classify(self.info(), self.frontier)
        self.assertEqual(result["quality"]["status"], "candidate")

    def test_rejects_scored_model_below_threshold(self):
        result = quality.classify(self.info(coding=50, agentic=30), self.frontier)
        self.assertEqual(result["quality"]["status"], "below_threshold")

    def test_requires_tools_and_minimum_context(self):
        without_tools = quality.classify(
            self.info(coding=80, agentic=60, tools=False), self.frontier
        )
        short_context = quality.classify(
            self.info(coding=80, agentic=60, context=64000), self.frontier
        )
        self.assertEqual(without_tools["quality"]["status"], "ineligible")
        self.assertEqual(short_context["quality"]["status"], "ineligible")

    def test_excludes_free_router_from_quality_candidates(self):
        info = self.info()
        info["is_router"] = True
        result = quality.classify(info, self.frontier)
        self.assertEqual(result["quality"]["status"], "ineligible")


class ThresholdDefaultsTests(unittest.TestCase):
    def test_default_thresholds_are_symmetric(self):
        self.assertEqual(quality.DEFAULT_CODING_RATIO, 0.80)
        self.assertEqual(quality.DEFAULT_AGENTIC_RATIO, 0.80)


if __name__ == "__main__":
    unittest.main()
