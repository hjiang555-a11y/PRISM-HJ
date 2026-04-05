"""
LLM translator: natural language → PSDL (via Ollama).

This module is the only place that communicates with the Ollama HTTP API.
It does **not** perform any physics computations.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

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
PSDL (Physical Scene Description Language) schema below.

RULES (strictly enforced):
1. Output ONLY raw JSON — no markdown fences, no explanations, no extra text.
2. Use SI units throughout (metres, kilograms, seconds, m/s).
3. For any parameter not explicitly mentioned, use the default values shown below.
4. The simulation should run long enough to cover the time-span implied by the
   question. Set `world.steps` = round(T / dt) where T is the implied duration
   and dt = 0.01 s (default).
5. Gravity is [0, 0, -9.8] unless stated otherwise.
6. The `query` field must be a concise restatement of what the user wants to know.

PSDL JSON SCHEMA (with defaults):
{
  "world": {
    "gravity": [0, 0, -9.8],
    "dt": 0.01,
    "steps": 100,
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
