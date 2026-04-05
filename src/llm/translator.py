"""
LLM translator: natural language → PSDL (via Ollama).

This module is the only place that communicates with the Ollama HTTP API.
It does **not** perform any physics computations.

Layer role (architecture layer 1 — NL Interface)
-------------------------------------------------
* :func:`text_to_psdl` — primary entry point; full NL → PSDL translation.
* :func:`classify_scenario` — lightweight scenario classifier; reserved for
  future "classify-then-template-fill" routing so the dispatcher can skip
  the full LLM call for known scenario types.
* :func:`generate_answer` — post-simulation NL answer generation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import requests
from pydantic import ValidationError

from src.schema.psdl import PSDL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OLLAMA_URL: str = "http://localhost:11434/api/generate"
MODEL_NAME: str = "deepseek-r1:32b"

# How long to wait (seconds) for the Ollama HTTP response.
_REQUEST_TIMEOUT: int = 300

SYSTEM_PROMPT: str = """\
You are a physics scene compiler. Your ONLY job is to convert the user's natural
language physics problem into a valid JSON object that strictly conforms to the
PSDL v0.1 (Physical Scene Description Language) schema below.

RULES (strictly enforced):
1. Output ONLY raw JSON — no markdown fences, no explanations, no extra text.
2. Use SI units throughout (metres, kilograms, seconds, m/s).
3. For any parameter not explicitly mentioned, use the default values shown below.
4. The simulation should run long enough to cover the time-span implied by the
   question. Set `world.steps` = round(T / dt) where T is the implied duration
   and dt = 0.01 s (default).
5. Gravity is [0, 0, -9.8] unless stated otherwise.
6. The `query` field must be a concise restatement of what the user wants to know.
7. Set `scenario_type` to the best matching type: "free_fall", "projectile",
   "collision", or null if unknown.
8. List explicit physical assumptions in `assumptions`.
9. `world.ground_plane` must be set explicitly: true only if the scenario
   involves contact with the ground.

PSDL JSON SCHEMA (with defaults):
{
  "schema_version": "0.1",
  "scenario_type": null,
  "assumptions": [],
  "source_refs": [],
  "validation_targets": [],
  "world": {
    "gravity": [0, 0, -9.8],
    "dt": 0.01,
    "steps": 100,
    "ground_plane": false,
    "space": {
      "min": [-10, -10, -10],
      "max": [10, 10, 10],
      "boundary_type": "elastic"
    },
    "observer": null,
    "theorems": ["newton_second", "energy_conservation"]
  },
  "objects": [
    {
      "type": "particle",
      "mass": 1.0,
      "radius": 0.1,
      "position": [0, 0, 0],
      "velocity": [0, 0, 0],
      "restitution": 0.9
    }
  ],
  "query": "what is the position and velocity after 1 second?"
}

Remember: output ONLY the JSON object, nothing else.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def text_to_psdl(user_query: str) -> PSDL:
    """
    Translate a natural language physics question into a validated :class:`PSDL`.

    The function follows a *template-first* strategy:

    1. Run the lightweight rule-based :func:`classify_scenario` classifier.
    2. If a known scenario type is detected, attempt to extract numeric
       parameters from the query and build the PSDL directly from the
       corresponding template (no LLM call required).
    3. If classification fails or parameter extraction is incomplete, fall
       back to the full LLM (Ollama) translation path.

    Parameters
    ----------
    user_query:
        The user's question in any language (Chinese, English, etc.).

    Returns
    -------
    PSDL
        A validated Pydantic model ready for simulation.

    Raises
    ------
    ConnectionError
        If the Ollama service is unreachable (LLM fallback path only).
    ValueError
        If the LLM returns malformed JSON or the JSON does not satisfy the
        PSDL schema (LLM fallback path only).
    """
    # ------------------------------------------------------------------
    # Step 1: Template-first path
    # ------------------------------------------------------------------
    scenario = classify_scenario(user_query)

    if scenario == "free_fall":
        psdl = _try_template_free_fall(user_query)
        if psdl is not None:
            logger.info(
                "text_to_psdl: free_fall template path used (no LLM call)."
            )
            return psdl
        logger.info(
            "text_to_psdl: free_fall template extraction incomplete, "
            "falling back to LLM."
        )

    elif scenario == "projectile":
        psdl = _try_template_projectile(user_query)
        if psdl is not None:
            logger.info(
                "text_to_psdl: projectile template path used (no LLM call)."
            )
            return psdl
        logger.info(
            "text_to_psdl: projectile template extraction incomplete, "
            "falling back to LLM."
        )

    elif scenario == "collision":
        psdl = _try_template_collision(user_query)
        if psdl is not None:
            logger.info(
                "text_to_psdl: collision template path used (no LLM call)."
            )
            return psdl
        logger.info(
            "text_to_psdl: collision template extraction incomplete, "
            "falling back to LLM."
        )

    # ------------------------------------------------------------------
    # Step 2: LLM fallback
    # ------------------------------------------------------------------
    return _text_to_psdl_via_llm(user_query)


# ---------------------------------------------------------------------------
# Template helper functions
# ---------------------------------------------------------------------------

def _try_template_free_fall(user_query: str) -> Optional[PSDL]:
    """Return a free_fall PSDL built from the template, or ``None``."""
    try:
        from src.templates.extractor import extract_free_fall_params
        from src.templates.free_fall import build_psdl as build_free_fall

        params = extract_free_fall_params(user_query)
        if params is None:
            return None
        return build_free_fall(**params)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_try_template_free_fall failed: %s", exc)
        return None


def _try_template_projectile(user_query: str) -> Optional[PSDL]:
    """Return a projectile PSDL built from the template, or ``None``."""
    try:
        from src.templates.extractor import extract_projectile_params
        from src.templates.projectile import build_psdl as build_projectile

        params = extract_projectile_params(user_query)
        if params is None:
            return None
        return build_projectile(**params)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_try_template_projectile failed: %s", exc)
        return None


def _try_template_collision(user_query: str) -> Optional[PSDL]:
    """Return a collision PSDL built from the template, or ``None``."""
    try:
        from src.templates.extractor import extract_collision_params
        from src.templates.collision import build_psdl as build_collision

        params = extract_collision_params(user_query)
        if params is None:
            return None
        return build_collision(**params)
    except Exception as exc:  # noqa: BLE001
        logger.debug("_try_template_collision failed: %s", exc)
        return None


def _text_to_psdl_via_llm(user_query: str) -> PSDL:
    """
    Full LLM-based PSDL translation via Ollama (fallback path).

    Raises
    ------
    ConnectionError
        If the Ollama service is unreachable.
    ValueError
        If the LLM returns malformed JSON or the JSON does not satisfy the
        PSDL schema.
    """
    payload: Dict[str, Any] = {
        "model": MODEL_NAME,
        "system": SYSTEM_PROMPT,
        "prompt": user_query,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.0,
            "seed": 42,
        },
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise ConnectionError(
            f"无法连接到 Ollama 服务（{OLLAMA_URL}）。\n"
            "请确保 'ollama serve' 正在运行。"
        ) from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        raise ConnectionError(
            f"Ollama 返回 HTTP {status}。\n"
            f"请确认模型 '{MODEL_NAME}' 已通过 'ollama pull {MODEL_NAME}' 拉取。"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise ConnectionError(
            f"Ollama 请求超时（>{_REQUEST_TIMEOUT}s）。请检查服务状态或增大超时时间。"
        ) from exc

    # Parse Ollama's envelope
    try:
        ollama_data = response.json()
        raw_text: str = ollama_data.get("response", "")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama 返回了无法解析的响应：{response.text[:500]}") from exc

    logger.debug("Raw LLM response:\n%s", raw_text)

    # Extract JSON from the response (handle possible surrounding whitespace)
    raw_text = raw_text.strip()

    try:
        psdl_dict = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        # Attempt to extract the first {...} block as a fallback
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                psdl_dict = json.loads(raw_text[start:end])
            except json.JSONDecodeError:
                raise ValueError(
                    f"LLM 返回的 JSON 格式无效，无法解析。\n原始内容（前500字）：{raw_text[:500]}"
                ) from exc
        else:
            raise ValueError(
                f"LLM 返回的内容不包含有效的 JSON 对象。\n原始内容（前500字）：{raw_text[:500]}"
            ) from exc

    try:
        psdl = PSDL.model_validate(psdl_dict)
    except ValidationError as exc:
        raise ValueError(
            f"LLM 生成的 JSON 未通过 PSDL 模式验证：\n{exc}\n\n原始 JSON：{psdl_dict}"
        ) from exc

    logger.info("PSDL 解析成功：%d 个对象，步数=%d", len(psdl.objects), psdl.world.steps)
    return psdl


def classify_scenario(user_query: str) -> str | None:
    """
    Lightweight rule-based scenario classifier.

    Uses regex patterns to identify the most likely physics scenario type
    from the user's natural language question, supporting both Chinese and
    English input.  If no pattern matches, returns ``None`` so the full
    LLM translation path is used as a fallback.

    Supported scenario types (v0.2)
    --------------------------------
    ``"free_fall"``
        Vertical drop under gravity, no horizontal component in initial
        velocity.  Examples: 自由落体, dropped from height, falls from rest.

    ``"projectile"``
        Horizontal or angled throw — object launched with non-zero horizontal
        velocity.  Examples: 抛体, 水平抛出, projectile motion.

    ``"collision"``
        Two or more objects interacting via impact.  Examples: 碰撞, collision,
        collide, elastic/inelastic.

    Parameters
    ----------
    user_query:
        The user's natural language question.

    Returns
    -------
    str or None
        Scenario type string or ``None`` if classification is uncertain.
    """
    if not user_query or not user_query.strip():
        return None
    text = user_query.lower()

    # ------------------------------------------------------------------ #
    # free_fall patterns (Chinese + English)                              #
    # ------------------------------------------------------------------ #
    _FREE_FALL_PATTERNS = [
        r'自由落体',
        r'自由下落',
        r'从.*高.*?(落下|下落|落体)',
        r'从高度',
        r'\bfree[\s\-]?fall\b',
        r'\bdrops?\s+from\b',
        r'\bdropped\s+from\b',
        r'\bfalls?\s+from\b',
        r'\bfallen?\s+from\b',
        r'\breleased?\s+from\b',
        r'\bdropped?\s+from\s+(a\s+)?height\b',
        r'\bvertical\s+drop\b',
    ]

    # ------------------------------------------------------------------ #
    # projectile patterns                                                 #
    # ------------------------------------------------------------------ #
    _PROJECTILE_PATTERNS = [
        r'抛体',
        r'水平抛',
        r'平抛',
        r'斜抛',
        r'以.*速度.*水平',
        r'水平.*速度.*抛',
        r'仰角',
        r'以.*度.*抛',
        r'以.*°.*抛',
        r'\bprojectile\b',
        r'\bhorizontally?\s+thrown?\b',
        r'\bthrown?\s+horizontally?\b',
        r'\blaunched?\s+(at\s+an?\s+angle|horizontally?)\b',
        r'\binitial\s+horizontal\s+velocity\b',
        r'\bat\s+an?\s+angle\s+of\b',
        r'\blaunched?\s+at\s+\d',
    ]

    # ------------------------------------------------------------------ #
    # collision patterns                                                  #
    # ------------------------------------------------------------------ #
    _COLLISION_PATTERNS = [
        r'碰撞',
        r'碰后',
        r'相撞',
        r'弹性碰',
        r'非弹性碰',
        r'\bcollision\b',
        r'\bcollide[sd]?\b',
        r'\bimpact\b',
        r'\bstrike[sd]?\b',
        r'\belastic\s+collision\b',
        r'\binelastic\s+collision\b',
    ]

    # Order matters: check more specific patterns first
    for pattern in _FREE_FALL_PATTERNS:
        if re.search(pattern, text):
            logger.debug("classify_scenario: matched free_fall (pattern=%r)", pattern)
            return "free_fall"

    for pattern in _PROJECTILE_PATTERNS:
        if re.search(pattern, text):
            logger.debug("classify_scenario: matched projectile (pattern=%r)", pattern)
            return "projectile"

    for pattern in _COLLISION_PATTERNS:
        if re.search(pattern, text):
            logger.debug("classify_scenario: matched collision (pattern=%r)", pattern)
            return "collision"

    logger.debug("classify_scenario: no pattern matched, returning None")
    return None


def generate_answer(user_query: str, final_states: list, temperature: float = 0.3) -> str:
    """
    Ask the LLM to produce a natural language answer given simulation results.

    Parameters
    ----------
    user_query:
        The original user question.
    final_states:
        List of ``{"position": [...], "velocity": [...]}`` dicts from the engine.
    temperature:
        Sampling temperature (default 0.3 for slight creativity).

    Returns
    -------
    str
        The LLM's natural language answer.

    Raises
    ------
    ConnectionError
        If the Ollama service is unreachable.
    """
    states_text = json.dumps(final_states, ensure_ascii=False, indent=2)
    prompt = (
        f"用户问题：{user_query}\n\n"
        f"物理模拟最终状态（SI单位）：\n{states_text}\n\n"
        "请根据上述模拟结果，用简洁的中文回答用户的问题。"
        "直接给出物理量数值（保留两位小数），并说明物理意义。"
        "不要重复问题，不要输出任何 JSON 或代码。"
    )

    payload: Dict[str, Any] = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise ConnectionError(
            f"无法连接到 Ollama 服务（{OLLAMA_URL}）。"
        ) from exc
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        raise ConnectionError(
            f"Ollama 返回 HTTP {status}。"
        ) from exc

    try:
        return response.json().get("response", "").strip()
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama 回答解析失败：{response.text[:500]}") from exc
