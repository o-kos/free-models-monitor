"""Quality scoring for free OpenRouter models.

The OpenRouter models catalog embeds Artificial Analysis coding and agentic
indices.  This module compares free models with the best currently listed
paid models, so thresholds move with the frontier instead of becoming stale.
"""

DEFAULT_CODING_RATIO = 0.90
DEFAULT_AGENTIC_RATIO = 0.80
DEFAULT_QUALITY_MIN_CONTEXT = 128000


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score(model, key):
    benchmarks = model.get("benchmarks", {})
    artificial_analysis = benchmarks.get("artificial_analysis", {})
    return _number(artificial_analysis.get(key))


def _is_paid(model):
    pricing = model.get("pricing", {})
    prompt = _number(pricing.get("prompt"))
    completion = _number(pricing.get("completion"))
    return (prompt is not None and prompt > 0) or (
        completion is not None and completion > 0
    )


def _supports_text(model):
    architecture = model.get("architecture", {})
    outputs = architecture.get("output_modalities")
    return not isinstance(outputs, list) or "text" in outputs


def build_paid_frontier(catalog):
    """Returns the current best paid coding and agentic benchmark scores."""
    coding = []
    agentic = []
    for model in catalog:
        if not _is_paid(model) or not _supports_text(model):
            continue
        coding_score = _score(model, "coding_index")
        agentic_score = _score(model, "agentic_index")
        if coding_score is not None:
            coding.append((coding_score, model.get("id", "unknown")))
        if agentic_score is not None:
            agentic.append((agentic_score, model.get("id", "unknown")))

    if not coding or not agentic:
        raise ValueError("paid coding/agentic benchmark data is unavailable")

    coding_score, coding_model = max(coding, key=lambda item: item[0])
    agentic_score, agentic_model = max(agentic, key=lambda item: item[0])
    return {
        "coding_index": coding_score,
        "coding_model": coding_model,
        "agentic_index": agentic_score,
        "agentic_model": agentic_model,
    }


def free_model_info(model):
    """Builds the snapshot fields needed for quality classification."""
    parameters = model.get("supported_parameters", [])
    architecture = model.get("architecture", {})
    supports_tools = isinstance(parameters, list) and (
        "tools" in parameters or "tool_choice" in parameters
    )
    return {
        "name": model.get("name", model.get("id", "unknown")),
        "context_length": model.get("context_length", 0) or 0,
        "supports_tools": supports_tools,
        "supports_text": _supports_text(model),
        "is_router": architecture.get("tokenizer") == "Router"
        or model.get("id") == "openrouter/free",
        "coding_index": _score(model, "coding_index"),
        "agentic_index": _score(model, "agentic_index"),
    }


def _relative(score, frontier_score):
    if score is None or not frontier_score:
        return None
    return round(score / frontier_score, 4)


def classify(
    model_info,
    frontier,
    coding_ratio=DEFAULT_CODING_RATIO,
    agentic_ratio=DEFAULT_AGENTIC_RATIO,
    min_context=DEFAULT_QUALITY_MIN_CONTEXT,
):
    """Annotates a free model as confirmed, candidate, below, or ineligible."""
    coding = _number(model_info.get("coding_index"))
    agentic = _number(model_info.get("agentic_index"))
    coding_relative = _relative(coding, frontier["coding_index"])
    agentic_relative = _relative(agentic, frontier["agentic_index"])

    capable = (
        bool(model_info.get("supports_tools"))
        and model_info.get("supports_text", True)
        and not model_info.get("is_router", False)
        and int(model_info.get("context_length", 0) or 0) >= min_context
    )
    coding_ok = coding_relative is not None and coding_relative >= coding_ratio
    agentic_ok = agentic_relative is not None and agentic_relative >= agentic_ratio

    if not capable:
        status = "ineligible"
    elif coding_ok and agentic_ok:
        status = "confirmed"
    elif (coding is None and agentic is None) or (
        coding_ok and agentic is None
    ) or (agentic_ok and coding is None):
        status = "candidate"
    else:
        status = "below_threshold"

    enriched = dict(model_info)
    enriched["quality"] = {
        "status": status,
        "coding_ratio": coding_relative,
        "agentic_ratio": agentic_relative,
        "coding_threshold": coding_ratio,
        "agentic_threshold": agentic_ratio,
        "min_context": min_context,
    }
    return enriched


def classify_free_catalog(
    free_models,
    frontier,
    coding_ratio=DEFAULT_CODING_RATIO,
    agentic_ratio=DEFAULT_AGENTIC_RATIO,
    min_context=DEFAULT_QUALITY_MIN_CONTEXT,
):
    """Returns a model-id mapping with quality annotations."""
    return {
        model_id: classify(
            info,
            frontier,
            coding_ratio=coding_ratio,
            agentic_ratio=agentic_ratio,
            min_context=min_context,
        )
        for model_id, info in free_models.items()
    }
