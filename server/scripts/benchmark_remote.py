#!/usr/bin/env python3
"""
Benchmark tool for LIM-AI Remote Server pipeline overhead.
Measures the pipeline overhead (JSON parsing, auth check, service validation)
for concept_map, generate_quiz, and generate_summary, with litellm.completion
mocked to return instantly.

Design Note:
    To measure only our code's overhead, we mock litellm.completion.
    This helps isolate network/LLM inference time from our validation and parsing logic.
    We configure essential startup environment variables in-memory before importing
    server components, then use FastAPI's TestClient to run the full request-response cycle.
    We use standard statistics module for latency calculations.
"""

import os
import sys
import time
import statistics
import math

# Set required environment variables before importing main to avoid fail-fast validation crashes
os.environ["API_KEY"] = "benchmark_secret_token"
os.environ["LLM_MODEL"] = "mock-model"
os.environ["LLM_API_KEY"] = "mock-api-key"
os.environ["WHISPER_MODEL_SIZE"] = "tiny"
os.environ["WHISPER_DEVICE"] = "cpu"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["SKETCHFAB_ACCESS_TOKEN"] = "mock-sketchfab-token"

# Add server directory to path to allow imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock litellm.completion
import litellm

class MockMessage:
    def __init__(self, content):
        self.content = content

class MockChoice:
    def __init__(self, content):
        self.message = MockMessage(content)

class MockResponse:
    def __init__(self, content):
        self.choices = [MockChoice(content)]


def mock_completion(*args, **kwargs):
    messages = kwargs.get("messages", [])
    prompt = messages[0]["content"] if messages else ""

    # Return different content based on the prompt/request type
    if "Mermaid" in prompt or "concept map" in prompt:
        # Valid Mermaid syntax
        return MockResponse("graph TD\n  A --> B\n  B --> C")
    elif "multiple-choice quiz" in prompt:
        # Valid JSON array for quiz
        return MockResponse(
            '[\n'
            '  {"question": "What is 2+2?", "options": ["3", "4", "5", "6"], "correct_index": 1},\n'
            '  {"question": "What is the capital of Italy?", "options": ["Rome", "Paris", "Berlin", "Madrid"], "correct_index": 0},\n'
            '  {"question": "What is H2O?", "options": ["Helium", "Hydrogen", "Water", "Oxygen"], "correct_index": 2},\n'
            '  {"question": "What is the speed of light?", "options": ["300k km/s", "150k km/s", "100k km/s", "50k km/s"], "correct_index": 0}\n'
            ']'
        )
    elif "riassunto" in prompt or "summary" in prompt:
        # Valid summary
        return MockResponse("Questo è il primo paragrafo del riassunto di prova.\n\nQuesto è il secondo paragrafo del riassunto.")

    return MockResponse("Default mock response content.")


litellm.completion = mock_completion


# Now import FastAPI App and TestClient
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
HEADERS = {"Authorization": "Bearer benchmark_secret_token"}


def calculate_percentile(data, percentile):
    """Calculate the percentile of a list of values."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_data[int(k)])
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return float(d0 + d1)


def measure_endpoint_overhead(action, payload, n_iterations=100):
    print(f"\n--- Benchmarking overhead for action '{action}' (N={n_iterations} iterations) ---")
    latencies = []

    # Warmup
    response = client.post("/api/v1/analyze", json=payload, headers=HEADERS)
    assert response.status_code == 200, f"Failed warmup: {response.text}"

    for _ in range(n_iterations):
        start = time.perf_counter()
        _ = client.post("/api/v1/analyze", json=payload, headers=HEADERS)
        end = time.perf_counter()
        latencies.append((end - start) * 1000.0)

    p_min = min(latencies)
    p_median = statistics.median(latencies)
    p95 = calculate_percentile(latencies, 95)
    p_max = max(latencies)

    print(f"'{action}' Pipeline Overhead (ms):")
    print(f"  Min:    {p_min:.2f} ms")
    print(f"  Median: {p_median:.2f} ms")
    print(f"  P95:    {p95:.2f} ms")
    print(f"  Max:    {p_max:.2f} ms")

    return {
        "min": p_min,
        "median": p_median,
        "p95": p95,
        "max": p_max
    }


def main():
    print("==================================================")
    print("           LIM-AI REMOTE SERVER OVERHEAD          ")
    print("==================================================")

    concept_map_payload = {
        "action": "concept_map",
        "data": {
            "topic": "La fotosintesi clorofilliana",
            "language": "it"
        }
    }

    quiz_payload = {
        "action": "generate_quiz",
        "data": {
            "lesson_context": "Fotosintesi clorofilliana: le piante usano luce, CO2 e acqua per produrre glucosio e ossigeno.",
            "num_questions": 4
        }
    }

    summary_payload = {
        "action": "generate_summary",
        "data": {
            "lesson_log": [
                {"timestamp": "2026-07-23T10:00:00Z", "type": "subtitle", "content": "Benvenuti alla lezione sulla fotosintesi."},
                {"timestamp": "2026-07-23T10:05:00Z", "type": "math", "content": "6CO2 + 6H2O -> C6H12O6 + 6O2"},
                {"timestamp": "2026-07-23T10:10:00Z", "type": "concept_map", "content": "Fotosintesi -> Piante -> Ossigeno"}
            ]
        }
    }

    cm_results = measure_endpoint_overhead("concept_map", concept_map_payload, 100)
    quiz_results = measure_endpoint_overhead("generate_quiz", quiz_payload, 100)
    summary_results = measure_endpoint_overhead("generate_summary", summary_payload, 100)

    print("\n==================================================")
    print("                 BENCHMARK SUMMARY                ")
    print("==================================================")
    print("These measurements isolate our API pipeline overhead (JSON parsing, auth, validation, etc.)")
    print("by mocking LiteLLM's network inference calls to return instantly.\n")

    print(f"concept_map Pipeline Overhead (P95):      {cm_results['p95']:.2f} ms")
    print(f"generate_quiz Pipeline Overhead (P95):    {quiz_results['p95']:.2f} ms")
    print(f"generate_summary Pipeline Overhead (P95): {summary_results['p95']:.2f} ms")

    print("\n==================================================")
    print("             CRITICAL NOTICE FOR USERS            ")
    print("==================================================")
    print("The NFR Target of <1.5 seconds is for complete end-to-end latency,")
    print("including actual LLM inference times from external providers.")
    print("Because real LLM inference times depend on external provider networks, API keys,")
    print("and token length, measuring end-to-end performance is a manual step for the user.")
    print("To perform end-to-end benchmarking against the <1.5s target:")
    print("  1. Configure real 'LLM_MODEL', 'LLM_API_KEY', and 'API_KEY' environment variables.")
    print("  2. Run the remote server with uvicorn main:app.")
    print("  3. Query the endpoint using an external load-testing tool (e.g., locust, autocannon, or custom script).")
    print("==================================================")


if __name__ == "__main__":
    main()
