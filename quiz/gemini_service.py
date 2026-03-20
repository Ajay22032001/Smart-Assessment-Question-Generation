"""
Task 7: Gemini API Integration for Question Generation.
Generates quiz questions using Google's Gemini API.
"""
import json
import re
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def build_prompt(topic: str, difficulty: str, num_questions: int) -> str:
    """Construct a specific prompt for Gemini including topic, difficulty, and count."""
    return f"""Generate exactly {num_questions} multiple-choice quiz questions on the topic "{topic}".
Difficulty level: {difficulty}.

Requirements:
- Each question must have exactly 4 options (A, B, C, D).
- Mark the correct answer clearly.
- Return ONLY valid JSON, no extra text.

Format your response as a JSON array like this:
[
  {{
    "question": "Your question text here?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_index": 0
  }}
]

Where correct_index is 0-3 (0=first option, 1=second, etc.).
Generate {num_questions} questions now:"""


def generate_questions(topic: str, difficulty: str, num_questions: int) -> list:
    """
    Call Gemini API to generate quiz questions.
    Returns list of dicts: {question, options, correct_index}
    Raises exception on API failure, rate limit, or invalid response.
    """
    api_key = getattr(settings, 'GEMINI_API_KEY', None) or ""
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured. Add GEMINI_API_KEY=your_key to .env in the project root.")

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
    except ImportError:
        raise ImportError("Install google-generativeai: pip install google-generativeai")

    prompt = build_prompt(topic, difficulty, num_questions)

    try:
        response = model.generate_content(prompt)
        text = response.text.strip() if (response and response.text) else ""
    except Exception as e:
        err_msg = str(e)
        if "API_KEY" in err_msg or "api_key" in err_msg:
            raise ValueError("Invalid or missing GEMINI_API_KEY. Add a valid key to .env") from e
        if "quota" in err_msg.lower() or "rate" in err_msg.lower():
            raise RuntimeError("API rate limit exceeded. Try again later.") from e
        logger.exception("Gemini API call failed: %s", e)
        raise RuntimeError(err_msg or "Failed to generate questions. Please try again.") from e

    if not text:
        block_reason = "Unknown"
        if response and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
            block_reason = str(response.prompt_feedback)
        raise ValueError(f"No response from Gemini ({block_reason}). Try a different topic or settings.")

    # Parse JSON from response (handle markdown code blocks)
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```\s*$', '', text)
    # Extract JSON array if wrapped in extra text
    arr_match = re.search(r'\[[\s\S]*\]', text)
    if arr_match:
        text = arr_match.group(0)
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON from Gemini: %s", text[:500])
        raise ValueError("Could not parse generated questions. Please try again.") from e

    if not isinstance(data, list):
        raise ValueError("Invalid response format: expected a list of questions.")

    questions = []
    for i, item in enumerate(data[:num_questions]):
        if not isinstance(item, dict):
            continue
        q = item.get('question', '').strip()
        opts = item.get('options', [])
        correct = item.get('correct_index', 0)
        if q and len(opts) >= 4:
            questions.append({
                'question': q,
                'options': opts[:4],
                'correct_index': min(max(0, int(correct)), 3),
            })

    if len(questions) < num_questions:
        raise ValueError(f"Only {len(questions)} valid questions generated. Please try again.")

    return questions[:num_questions]

def generate_explanation(question_text, correct_answer, user_answer=None):
    """
    Generate an explanation for the correct answer.
    """
    prompt = f"""
    Question: {question_text}
    Correct answer: {correct_answer}
    """
    if user_answer:
        prompt += f"\nThe user chose: {user_answer} (incorrect)."
    prompt += "\nPlease provide a brief explanation of why the correct answer is right, and if the user was wrong, clarify the misconception. Keep it concise (2-3 sentences)."

    try:
        import google.generativeai as genai
        from django.conf import settings
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Explanation generation failed: {e}")
        return "Explanation could not be generated at this time."