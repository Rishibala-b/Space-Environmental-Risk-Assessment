"""
LLMService: query understanding (text -> structured intent) and response
generation (facts -> prose). This is the ONLY file that calls an external LLM API.

Anti-hallucination design:
- understand_query() only extracts intent + NORAD IDs + a parameter, as JSON.
  Any NORAD ID the LLM returns is kept ONLY if it literally appears in the user's
  text, and the parameter is mapped onto a real feature key -- so the LLM cannot
  invent an object or a field.
- generate_response() is given the retrieved facts verbatim and told to use ONLY
  those values.
- With LLM_PROVIDER=none or no API key, both functions use transparent
  rule-based logic (regex + templates).

Testability: provider / api_key / model / client are injectable, so tests can
force rule-based mode regardless of what the developer's .env contains.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.tle_service import find_norad_ids
from app.utils.config import settings

VALID_INTENTS = {"object_lookup", "parameter_query", "comparison", "general_dataset", "tle_lookup", "unknown"}

# Phrase -> real feature/field key. Longer phrases first so "specific orbital
# energy" wins over "energy", "semi-major axis" over "axis", etc.
_PARAMETER_KEYWORDS = {
    "specific orbital energy": "specific_orbital_energy_km2_s2",
    "argument of perigee": "arg_perigee_deg",
    "arg of perigee": "arg_perigee_deg",
    "right ascension": "raan_deg",
    "semi-major axis": "semi_major_axis_km",
    "semi major axis": "semi_major_axis_km",
    "semimajor axis": "semi_major_axis_km",
    "orbital velocity": "orbital_velocity_km_s",
    "orbital period": "orbital_period_min",
    "mean anomaly": "mean_anomaly_deg",
    "true anomaly": "true_anomaly_deg",
    "mean motion": "mean_motion_rev_per_day",
    "object type": "OBJECT_TYPE",
    "decay date": "DECAY_DATE",
    "inclination": "inclination_deg",
    "eccentricity": "eccentricity",
    "altitude": "altitude_km",
    "height": "altitude_km",
    "velocity": "orbital_velocity_km_s",
    "speed": "orbital_velocity_km_s",
    "period": "orbital_period_min",
    "energy": "specific_orbital_energy_km2_s2",
    "epoch": "EPOCH",
    "raan": "raan_deg",
    "name": "OBJECT_NAME",
    "type": "OBJECT_TYPE",
}

_KNOWN_FIELD_KEYS = set(_PARAMETER_KEYWORDS.values())


def map_parameter(raw: Optional[str]) -> Optional[str]:
    """Maps a free-form parameter word (from the LLM or the user) onto a real
    field key, or None if it can't be mapped."""
    if not raw:
        return None
    text = str(raw).strip()
    if text in _KNOWN_FIELD_KEYS:
        return text
    lowered = text.lower().replace("_", " ")
    for phrase, key in _PARAMETER_KEYWORDS.items():
        if phrase in lowered:
            return key
    return None


def _strip_code_fences(text: str) -> str:
    """LLMs often wrap JSON in ```json ... ``` -- remove that before parsing."""
    t = text.strip()
    fenced = re.match(r"^```(?:json|JSON)?\s*(.*?)\s*```$", t, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    # otherwise take the outermost {...} if there is surrounding chatter
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        return t[start:end + 1]
    return t


@dataclass
class ParsedIntent:
    intent: str
    norad_ids: List[str] = field(default_factory=list)
    parameter: Optional[str] = None
    raw_query: str = ""


class LLMService:
    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None, client: Any = None):
        self.provider = (provider if provider is not None else settings.llm_provider or "none").lower()
        self.api_key = api_key if api_key is not None else settings.llm_api_key
        self.model = model or settings.llm_model
        self.enabled = self.provider != "none" and (bool(self.api_key) or client is not None)
        self._client = client
        if not self.enabled or self._client is not None:
            return
        if self.provider == "anthropic":
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                print("[LLMService] 'anthropic' package not installed -- falling back to rule-based mode.")
                self.enabled = False
        elif self.provider == "google":
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                print("[LLMService] 'google-genai' package not installed -- falling back to rule-based mode.")
                self.enabled = False
        else:
            print(f"[LLMService] Unknown LLM_PROVIDER='{self.provider}' -- falling back to rule-based mode.")
            self.enabled = False

    def mode(self) -> str:
        return f"llm:{self.provider}" if self.enabled else "rule_based_fallback"

    def _call_llm(self, prompt: str, max_tokens: int) -> str:
        if self.provider == "anthropic":
            resp = self._client.messages.create(
                model=self.model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        if self.provider == "google":
            resp = self._client.models.generate_content(model=self.model, contents=prompt)
            return (resp.text or "").strip()
        raise RuntimeError(f"No LLM call implemented for provider '{self.provider}'.")

    # ------------------------------------------------------------- understanding --
    def understand_query(self, query: str) -> ParsedIntent:
        if self.enabled:
            try:
                return self._understand_via_llm(query)
            except Exception as e:
                print(f"[LLMService] LLM query-understanding failed ({e}); using rule-based fallback.")
        return self._understand_via_rules(query)

    def _understand_via_llm(self, query: str) -> ParsedIntent:
        prompt = f"""Extract structured information from this question about an object
in Earth orbit. Respond with ONLY a JSON object, no code fences, no other text:
{{"intent": one of {sorted(VALID_INTENTS)},
  "norad_ids": [NORAD catalog ID strings literally written in the question, if any],
  "parameter": the orbital parameter asked about (e.g. "inclination", "altitude",
               "period", "eccentricity"), or null}}

Do not answer the question. Only extract what is being asked for.

Question: {query}"""
        data = json.loads(_strip_code_fences(self._call_llm(prompt, max_tokens=300)))
        if not isinstance(data, dict):
            raise ValueError("LLM did not return a JSON object")

        intent = data.get("intent") if data.get("intent") in VALID_INTENTS else "unknown"

        # Anti-hallucination: only keep IDs that literally occur in the user's text.
        in_text = find_norad_ids(query)
        llm_ids = [str(int(x)) for x in data.get("norad_ids", []) if str(x).strip().isdigit()]
        norad_ids = [i for i in llm_ids if i in in_text] or in_text

        # Map the LLM's plain-language parameter onto a real field key; fall back
        # to scanning the user's own words.
        parameter = map_parameter(data.get("parameter")) or map_parameter(query)

        # Sanity-fix the intent using the verified facts above.
        if intent == "comparison" and len(norad_ids) < 2:
            intent = "parameter_query" if (parameter and norad_ids) else ("object_lookup" if norad_ids else "unknown")
        if intent in ("unknown", "tle_lookup") and norad_ids:
            intent = "parameter_query" if parameter else "object_lookup"
        if intent == "parameter_query" and not parameter and norad_ids:
            intent = "object_lookup"

        return ParsedIntent(intent=intent, norad_ids=norad_ids, parameter=parameter, raw_query=query)

    def _understand_via_rules(self, query: str) -> ParsedIntent:
        q = query.lower()
        norad_ids = find_norad_ids(query)
        parameter = map_parameter(q) if norad_ids else None

        if any(w in q for w in ("compare", "comparison", "versus", " vs ", " vs.")):
            intent = "comparison"  # with fewer than two IDs this fails cleanly, asking for two
        elif any(w in q for w in ("what information", "what data", "what columns", "dataset contain",
                                   "what fields", "schema")):
            intent = "general_dataset"
        elif parameter is not None and norad_ids:
            intent = "parameter_query"
        elif norad_ids:
            intent = "object_lookup"
        else:
            intent = "unknown"

        return ParsedIntent(intent=intent, norad_ids=norad_ids, parameter=parameter, raw_query=query)

    # ------------------------------------------------------------- response gen --
    def generate_response(self, intent: str, facts: Dict[str, Any]) -> str:
        # Errors are returned verbatim -- no reason to spend an LLM call on them,
        # and it guarantees the error text is never paraphrased into something wrong.
        if facts.get("error"):
            return self._generate_via_template(intent, facts)
        if self.enabled:
            try:
                return self._generate_via_llm(intent, facts)
            except Exception as e:
                print(f"[LLMService] LLM response generation failed ({e}); using template fallback.")
        return self._generate_via_template(intent, facts)

    def _generate_via_llm(self, intent: str, facts: Dict[str, Any]) -> str:
        visible = {k: v for k, v in facts.items() if not k.startswith("_") and k not in ("TLE_LINE1", "TLE_LINE2")}
        prompt = f"""You are explaining data about an object in Earth orbit. You are given
a JSON object of facts retrieved live from Space-Track.org and/or computed by a
trained classification model. Write a clear, concise plain-language response
using ONLY the values in this JSON.

STRICT RULES:
- Do NOT add any fact or number not present in the JSON below.
- If a value is missing or null, say it is not available. Do not guess or estimate.
- You MAY briefly explain what a technical term means in general, but never
  invent the object's specific value for it.
- If a "warning" field is present, state it clearly.

Intent: {intent}
Facts (JSON): {json.dumps(visible, default=str)}"""
        text = self._call_llm(prompt, max_tokens=600)
        if not text:
            raise ValueError("empty LLM response")
        return text

    def _generate_via_template(self, intent: str, facts: Dict[str, Any]) -> str:
        """Deterministic, dependency-free phrasing. Every value comes straight from `facts`."""
        if facts.get("error"):
            return str(facts["error"])

        if intent == "unknown":
            return ("I couldn't identify a NORAD ID or TLE in that message. Try naming a "
                    "NORAD ID (e.g. 'Tell me about NORAD 25544') or pasting a TLE.")

        warning = facts.get("warning")
        suffix = f"\n\nWarning: {warning}" if warning else ""

        if intent == "comparison":
            lines = ["Comparison of available parameters:"]
            for field_name, values in facts.get("comparison", {}).items():
                lines.append(f"  {field_name}: {values}")
            if len(lines) == 1:
                lines.append("  No common parameters were available for both objects.")
            return "\n".join(lines) + suffix

        if intent == "classification":
            probs = facts.get("probabilities", {}) or {}
            text = (
                f"The object is classified as {facts.get('prediction', 'UNKNOWN')} "
                f"with {facts.get('confidence', '?')}% confidence "
                f"(satellite: {probs.get('satellite', '?')}%, debris: {probs.get('debris', '?')}%), "
                f"using the {facts.get('model', 'trained')} model."
            )
            return text + suffix

        if intent == "batch_summary":
            c = facts.get("counts", {}) or {}
            text = (
                f"Analyzed {facts.get('requested', 0)} object(s): "
                f"{c.get('satellite', 0)} classified as active satellite, "
                f"{c.get('debris', 0)} as space debris, "
                f"{c.get('failed', 0)} could not be classified."
            )
            if facts.get("truncated"):
                text += f" Results were limited to the first {facts.get('limit')} objects."
            return text

        # object_lookup / parameter_query / tle_lookup: "print what we have"
        lines = [f"{key}: {value}" for key, value in facts.items()
                 if not key.startswith("_") and key not in ("warning",)]
        if not lines:
            return "That information is not available from Space-Track for this object."
        return "\n".join(lines) + "\n\nSource: Live data from Space-Track.org." + suffix
