"""
LLM interface — natural language classification and answer generation (via Ollama).

This module communicates with the Ollama HTTP API.
It does **not** perform any physics computations.

Functions
---------
* :func:`classify_scenario` — lightweight rule-based scenario classifier
  used by the problem semantic extraction pipeline.
* :func:`generate_answer` — post-simulation NL answer generation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OLLAMA_URL: str = "http://localhost:11434/api/generate"
MODEL_NAME: str = "deepseek-r1:32b"

# How long to wait (seconds) for the Ollama HTTP response.
_REQUEST_TIMEOUT: int = 300

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
        r'\bprojectile\b',
        r'\bhorizontally?\s+thrown?\b',
        r'\bthrown?\s+horizontally?\b',
        r'\blaunched?\s+(at\s+an?\s+angle|horizontally?)\b',
        r'\binitial\s+horizontal\s+velocity\b',
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
