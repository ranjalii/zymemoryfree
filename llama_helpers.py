"""llama_helpers.py - Optional Llama 8B helpers for memory enhancement

Uses local Llama via Ollama for:
- Summarizing long text
- Extracting keywords
- Generating tags

No API keys required - fully self-hosted and optional.
"""
import json
from typing import Optional, List, Dict
import requests

# Ollama API endpoint (default local installation)
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.1:8b-instruct-fp16"  # or "llama3.1:8b"


def is_llama_available() -> bool:
    """Check if Ollama is running and model is available."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            models = response.json().get("models", [])
            return any(OLLAMA_MODEL in m.get("name", "") for m in models)
        return False
    except:
        return False


def call_llama(prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 500) -> str:
    """
    Call local Llama model via Ollama API.

    Args:
        prompt: User prompt
        system: System instruction (optional)
        temperature: Sampling temperature
        max_tokens: Max response length

    Returns:
        Generated text response (or empty string on failure)
    """
    try:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        response = requests.post(OLLAMA_API_URL, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        return result.get("response", "").strip()

    except Exception as e:
        print(f"Llama API error: {e}")
        return ""


def summarize_text(text: str, max_length: int = 100) -> Optional[str]:
    """
    Summarize text using Llama.

    Args:
        text: Text to summarize
        max_length: Max summary length in words

    Returns:
        Summary string or None if failed
    """
    if not is_llama_available():
        return None

    system = "You are a helpful assistant that creates concise summaries."
    prompt = f"Summarize the following text in {max_length} words or less:\n\n{text}"

    summary = call_llama(prompt, system, temperature=0.2)
    return summary if summary else None


def extract_keywords(text: str, max_keywords: int = 5) -> List[str]:
    """
    Extract keywords from text using Llama.

    Args:
        text: Text to analyze
        max_keywords: Maximum number of keywords

    Returns:
        List of keyword strings
    """
    if not is_llama_available():
        return []

    system = "You extract important keywords from text. Return only a JSON array of keywords."
    prompt = f"Extract up to {max_keywords} important keywords from this text:\n\n{text}\n\nRespond with JSON format: {{\"keywords\": [\"word1\", \"word2\"]}}"

    response = call_llama(prompt, system, temperature=0.2, max_tokens=200)

    if not response:
        return []

    try:
        # Try to parse JSON response
        start = response.find('{')
        end = response.rfind('}') + 1
        if start != -1 and end > 0:
            data = json.loads(response[start:end])
            return data.get("keywords", [])[:max_keywords]
    except:
        pass

    # Fallback: try to extract comma-separated words
    try:
        words = [w.strip().strip('"\'') for w in response.split(',')]
        return [w for w in words if w][:max_keywords]
    except:
        return []


def extract_entities_llm(text: str) -> List[Dict]:
    """
    Extract named entities from text using Llama (more accurate than regex).

    Args:
        text: Text to analyze

    Returns:
        List of dicts with 'text', 'type' (PERSON, ORG, LOCATION, etc.)
    """
    if not is_llama_available():
        return []

    system = "You extract named entities from text. Return only JSON."
    prompt = f"""Extract named entities from this text and classify them.

Text: {text}

Return JSON format:
{{
  "entities": [
    {{"text": "entity name", "type": "PERSON"}},
    {{"text": "entity name", "type": "ORGANIZATION"}},
    {{"text": "entity name", "type": "LOCATION"}}
  ]
}}

Types: PERSON, ORGANIZATION, LOCATION, DATE, EMAIL, PHONE, URL, CONCEPT
Only extract clearly identifiable entities."""

    response = call_llama(prompt, system, temperature=0.1, max_tokens=500)

    if not response:
        return []

    try:
        # Parse JSON response
        start = response.find('{')
        end = response.rfind('}') + 1
        if start != -1 and end > 0:
            data = json.loads(response[start:end])
            entities = data.get("entities", [])
            # Normalize entity types
            for e in entities:
                if e.get('type'):
                    e['type'] = e['type'].upper()
            return entities
    except Exception as e:
        print(f"Failed to parse LLM entity response: {e}")

    return []


def extract_relationships_llm(text: str, entities: List[str]) -> List[Dict]:
    """
    Extract relationships between entities using Llama.

    Args:
        text: Text containing entities
        entities: List of entity names

    Returns:
        List of dicts with 'from', 'to', 'type' (e.g., WORKS_AT, LOCATED_IN)
    """
    if not is_llama_available() or len(entities) < 2:
        return []

    entity_list = ", ".join(entities[:10])  # Limit for context

    system = "You extract relationships between entities. Return only JSON."
    prompt = f"""Given this text, identify relationships between these entities: {entity_list}

Text: {text}

Return JSON format:
{{
  "relationships": [
    {{"from": "Entity A", "to": "Entity B", "type": "WORKS_AT"}},
    {{"from": "Entity C", "to": "Entity D", "type": "LOCATED_IN"}}
  ]
}}

Relationship types: WORKS_AT, LOCATED_IN, OWNS, MANAGES, KNOWS, WORKS_WITH, PART_OF, CAUSES, LEADS_TO
Only extract clear, explicit relationships."""

    response = call_llama(prompt, system, temperature=0.1, max_tokens=500)

    if not response:
        return []

    try:
        start = response.find('{')
        end = response.rfind('}') + 1
        if start != -1 and end > 0:
            data = json.loads(response[start:end])
            relationships = data.get("relationships", [])
            # Normalize relationship types
            for r in relationships:
                if r.get('type'):
                    r['type'] = r['type'].upper()
            return relationships
    except Exception as e:
        print(f"Failed to parse LLM relationship response: {e}")

    return []


def enhance_memory(content: str) -> Dict:
    """
    Enhance memory with optional AI-generated metadata.

    Args:
        content: Memory content

    Returns:
        Dict with optional 'summary' and 'keywords' fields
    """
    metadata = {}

    if len(content) > 500:
        summary = summarize_text(content, max_length=50)
        if summary:
            metadata["summary"] = summary

    keywords = extract_keywords(content, max_keywords=5)
    if keywords:
        metadata["keywords"] = keywords

    return metadata


if __name__ == '__main__':
    # Test Llama connection
    if is_llama_available():
        print("✓ Llama is available")

        test_text = "Python is a high-level programming language. It's great for data science and web development."
        print(f"\nTest text: {test_text}")

        summary = summarize_text(test_text)
        print(f"Summary: {summary}")

        keywords = extract_keywords(test_text)
        print(f"Keywords: {keywords}")
    else:
        print("✗ Llama is not available. Install Ollama and run: ollama pull llama3.1:8b-instruct-fp16")
