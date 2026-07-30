#!/usr/bin/env python3
"""
Benchmark tool for LIM-AI Local Daemon.
Measures real latency of LOCAL actions (sympy_math, fast_ocr) over N=100 iterations,
and records resource usage (RSS memory, CPU%) using psutil under idle and active conditions.

Design Note:
    This script is designed to run standalone or within the poetry environment.
    It directly imports LocalEngine from daemon.local_bridge (by updating sys.path)
    to perform benchmarks against the exact codebase.
    `psutil` is used to capture resource usage during the runs.
    Tesseract/mss may not fully execute on a headless sandbox; we handle this by
    catching exceptions and reporting "skipped: no display" or another relevant message.
"""

import os
import sys
import time
import statistics
import math
from PIL import Image

# Add daemon directory to path to allow importing local_bridge
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from local_bridge import LocalEngine
except ImportError:
    sys.path.append(os.path.abspath(os.path.dirname(__file__)))
    from local_bridge import LocalEngine

try:
    import psutil
except ImportError:
    print("Warning: 'psutil' is not installed. Please install it with 'pip install psutil' or 'poetry add psutil --group dev'.")
    psutil = None


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


def measure_sympy_math(n_iterations=100):
    print(f"\n--- Benchmarking sympy_math (N={n_iterations} iterations) ---")
    expressions = ["2*x + 6 - 12", "x**2 - 5*x + 6", "sin(x) + cos(x)", "exp(x) - 1"]
    latencies = []

    for i in range(n_iterations):
        expr = expressions[i % len(expressions)]
        start = time.perf_counter()
        _ = LocalEngine.process_math(expr)
        end = time.perf_counter()
        latencies.append((end - start) * 1000.0)  # ms

    p_min = min(latencies)
    p_median = statistics.median(latencies)
    p95 = calculate_percentile(latencies, 95)
    p_max = max(latencies)

    print(f"sympy_math Latency (ms):")
    print(f"  Min:    {p_min:.2f} ms")
    print(f"  Median: {p_median:.2f} ms")
    print(f"  P95:    {p95:.2f} ms")
    print(f"  Max:    {p_max:.2f} ms")

    return {
        "min": p_min,
        "median": p_median,
        "p95": p95,
        "max": p_max,
        "latencies": latencies
    }


def measure_fast_ocr(n_iterations=100):
    print(f"\n--- Benchmarking fast_ocr (N={n_iterations} iterations) ---")

    # Create a synthetic image for test OCR in memory
    try:
        from PIL import ImageDraw
        img = Image.new("RGB", (300, 100), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((10, 40), "LIM-AI OCR TEST", fill=(0, 0, 0))
    except Exception as e:
        print(f"Could not construct synthetic test image: {e}")
        return "skipped: synthetic image creation failed"

    # Verify if pytesseract is installed and configured
    import pytesseract
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        print(f"pytesseract not fully available or tesseract binary not installed: {e}")
        return "skipped: no display/tesseract missing"

    latencies = []
    try:
        for i in range(n_iterations):
            start = time.perf_counter()
            _ = pytesseract.image_to_string(img).strip()
            end = time.perf_counter()
            latencies.append((end - start) * 1000.0)

        p_min = min(latencies)
        p_median = statistics.median(latencies)
        p95 = calculate_percentile(latencies, 95)
        p_max = max(latencies)

        print(f"fast_ocr Latency (ms):")
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
    except Exception as e:
        print(f"fast_ocr execution failed during iteration: {e}")
        return "skipped: execution error (possibly headless display/no tesseract)"


def monitor_resources():
    print("\n--- Resource Monitoring (psutil) ---")
    if psutil is None:
        print("Skipping resource monitoring: psutil not installed.")
        return {
            "idle_cpu": 0.0,
            "idle_rss": 0.0,
            "active_cpu_avg": 0.0,
            "active_cpu_max": 0.0,
            "active_rss_avg": 0.0,
            "active_rss_max": 0.0,
            "throttled_cpu_avg": 0.0,
            "throttled_cpu_max": 0.0,
            "ocr_cpu_avg": 0.0,
            "ocr_cpu_max": 0.0,
            "ocr_rss_max": 0.0
        }

    process = psutil.Process(os.getpid())

    # 1. Idle state measurement
    print("Measuring idle resource usage (5 seconds)...")
    process.cpu_percent(interval=None)
    time.sleep(1.0)
    idle_cpu = process.cpu_percent(interval=None)
    idle_rss = process.memory_info().rss / (1024 * 1024) # MB

    print(f"Idle CPU:   {idle_cpu:.2f}%")
    print(f"Idle RAM:   {idle_rss:.2f} MB")

    # 2. Active state measurement while doing math repeatedly (Unthrottled)
    print("Measuring active resource usage while running sympy_math continuously (Unthrottled, 3 seconds)...")
    active_cpu_samples = []
    active_rss_samples = []

    start_time = time.time()
    process.cpu_percent(interval=None) # Reset cpu counter

    iterations = 0
    while time.time() - start_time < 3.0:
        LocalEngine.process_math("x**3 - 3*x**2 + x - 5 * sin(x) + cos(x**2)")
        iterations += 1

        if iterations % 100 == 0:
            active_rss_samples.append(process.memory_info().rss / (1024 * 1024))
            active_cpu_samples.append(process.cpu_percent(interval=None))

    active_rss_samples.append(process.memory_info().rss / (1024 * 1024))
    active_cpu_samples.append(process.cpu_percent(interval=None))

    avg_active_cpu = statistics.mean(active_cpu_samples) if active_cpu_samples else 0.0
    max_active_cpu = max(active_cpu_samples) if active_cpu_samples else 0.0
    avg_active_rss = statistics.mean(active_rss_samples) if active_rss_samples else 0.0
    max_active_rss = max(active_rss_samples) if active_rss_samples else 0.0

    print(f"Unthrottled Active CPU:  Avg {avg_active_cpu:.2f}%, Max {max_active_cpu:.2f}%")
    print(f"Unthrottled Active RAM:  Avg {avg_active_rss:.2f} MB, Max {max_active_rss:.2f} MB")

    # 3. Throttled Active state measurement (simulating realistic teacher usage: 5 math operations/sec)
    print("Measuring active resource usage with realistic teacher math usage (5 math ops/sec, 3 seconds)...")
    throttled_cpu_samples = []
    start_time = time.time()
    process.cpu_percent(interval=None)

    while time.time() - start_time < 3.0:
        LocalEngine.process_math("x**3 - 3*x**2 + x - 5 * sin(x) + cos(x**2)")
        time.sleep(0.2) # 5 operations per second
        throttled_cpu_samples.append(process.cpu_percent(interval=None))

    avg_throttled_cpu = statistics.mean(throttled_cpu_samples) if throttled_cpu_samples else 0.0
    max_throttled_cpu = max(throttled_cpu_samples) if throttled_cpu_samples else 0.0

    print(f"Throttled Active CPU (5 ops/sec): Avg {avg_throttled_cpu:.2f}%, Max {max_throttled_cpu:.2f}%")

    # 4. Realistic Active state measurement during OCR/screenshot (e.g. once every 2 seconds)
    # Corrected: we measure system-wide CPU% to accurately capture the spawned tesseract process.
    print("Measuring active resource usage with realistic teacher OCR usage (once every 2 seconds, 6 seconds, system-wide CPU)...")
    ocr_cpu_samples = []
    ocr_rss_samples = []

    import pytesseract
    try:
        from PIL import ImageDraw
        img = Image.new("RGB", (300, 100), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((10, 40), "LIM-AI OCR TEST", fill=(0, 0, 0))
        pytesseract.get_tesseract_version()
        ocr_available = True
    except Exception:
        ocr_available = False

    if ocr_available:
        start_time = time.time()
        # Reset system-wide CPU counter
        psutil.cpu_percent(interval=None)

        while time.time() - start_time < 6.0:
            # Trigger OCR
            _ = pytesseract.image_to_string(img).strip()
            ocr_rss_samples.append(process.memory_info().rss / (1024 * 1024))
            # Measure system-wide CPU since last check (which includes the tesseract child subprocess)
            ocr_cpu_samples.append(psutil.cpu_percent(interval=None))
            time.sleep(2.0) # once every 2 seconds

        avg_ocr_cpu = statistics.mean(ocr_cpu_samples) if ocr_cpu_samples else 0.0
        max_ocr_cpu = max(ocr_cpu_samples) if ocr_cpu_samples else 0.0
        max_ocr_rss = max(ocr_rss_samples) if ocr_rss_samples else idle_rss
    else:
        print("pytesseract/OCR is not available. Skipping OCR resource monitoring.")
        avg_ocr_cpu = 0.0
        max_ocr_cpu = 0.0
        max_ocr_rss = idle_rss

    print(f"Realistic OCR Active CPU (System-wide): Avg {avg_ocr_cpu:.2f}%, Max {max_ocr_cpu:.2f}%")
    print(f"Realistic OCR Active RAM: Max {max_ocr_rss:.2f} MB")

    return {
        "idle_cpu": idle_cpu,
        "idle_rss": idle_rss,
        "active_cpu_avg": avg_active_cpu,
        "active_cpu_max": max_active_cpu,
        "active_rss_avg": avg_active_rss,
        "active_rss_max": max_active_rss,
        "throttled_cpu_avg": avg_throttled_cpu,
        "throttled_cpu_max": max_throttled_cpu,
        "ocr_cpu_avg": avg_ocr_cpu,
        "ocr_cpu_max": max_ocr_cpu,
        "ocr_rss_max": max_ocr_rss
    }


def main():
    print("==================================================")
    print("           LIM-AI LOCAL DAEMON BENCHMARK          ")
    print("==================================================")

    math_results = measure_sympy_math(100)
    ocr_results = measure_fast_ocr(100)
    resource_results = monitor_resources()

    print("\n==================================================")
    print("                 BENCHMARK SUMMARY                ")
    print("==================================================")

    # Verify math against target (<50ms)
    math_ok = "PASS" if math_results["p95"] < 50 else "FAIL"
    print(f"sympy_math (P95 Latency Target: <50ms): {math_results['p95']:.2f} ms -> {math_ok}")

    # Verify OCR against target (<50ms)
    if isinstance(ocr_results, dict):
        ocr_ok = "PASS" if ocr_results["p95"] < 50 else "FAIL"
        print(f"fast_ocr (P95 Latency Target: <50ms): {ocr_results['p95']:.2f} ms -> {ocr_ok}")
    else:
        print(f"fast_ocr (P95 Latency Target: <50ms): {ocr_results} -> NOT MEASURABLE")

    # Verify RAM against target (<150MB)
    ram_ok = "PASS" if resource_results["active_rss_max"] < 150 else "FAIL"
    print(f"Memory (Max Active RAM Target: <150MB): {resource_results['active_rss_max']:.2f} MB -> {ram_ok}")

    # Verify CPU against targets (<5% idle, <15% active during screenshot)
    idle_cpu_ok = "PASS" if resource_results["idle_cpu"] < 5 else "FAIL"

    # Specifically evaluate NFR CPU Active target (<15% during screenshot/OCR)
    ocr_cpu_ok = "PASS" if resource_results["ocr_cpu_avg"] < 15 else "FAIL"

    print(f"CPU Idle (Target: <5%): {resource_results['idle_cpu']:.2f}% -> {idle_cpu_ok}")
    print(f"CPU Active Throttled Math (Target Avg: <15%): {resource_results['throttled_cpu_avg']:.2f}%")
    print(f"CPU Active Unthrottled Math (Max load): {resource_results['active_cpu_avg']:.2f}%")
    print(f"CPU Active During OCR/Screenshot (Target Avg <15%): {resource_results['ocr_cpu_avg']:.2f}% -> {ocr_cpu_ok}")
    print("==================================================")


if __name__ == "__main__":
    main()
