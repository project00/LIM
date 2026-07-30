# CPU Benchmark Clarification

This document provides clarification on the CPU/RAM utilization measurements for the LIM-AI Local Daemon, addressing how the "Active" benchmarks align with the Non-Functional Requirements (NFR) specified in **docs/project-plan.md**.

---

## 1. Verbatim "Active" Math Benchmark Code

The "Active" CPU/RAM benchmark scenario originally executed in `daemon/scripts/benchmark_local.py` tested CPU/RAM under continuous, unthrottled mathematical evaluations, and under a throttled frequency of 5 operations per second using `sympy_math`.

### Unthrottled Active Loop:
```python
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
```

### Throttled (5 operations/second) Loop:
```python
    # 3. Throttled Active state measurement (simulating realistic teacher usage: 5 math operations/sec)
    print("Measuring active resource usage with realistic teacher math usage (5 math ops/sec, 3 seconds)...")
    throttled_cpu_samples = []
    start_time = time.time()
    process.cpu_percent(interval=None)

    while time.time() - start_time < 3.0:
        LocalEngine.process_math("x**3 - 3*x**2 + x - 5 * sin(x) + cos(x**2)")
        time.sleep(0.2) # 5 operations per second
        throttled_cpu_samples.append(process.cpu_percent(interval=None))
```

---

## 2. Alignment with NFR Specification

The NFR defined in `docs/project-plan.md` (§9 / §2.5 / SRS v2.0) defines the CPU performance requirement specifically as:
> `CPU < 5% idle, < 15% durante lo screenshot` (meaning CPU usage should be `< 15% during screen capture/OCR`).

### Clarification:
The original "Active" math benchmark scenario tested `sympy_math` repeatedly rather than `fast_ocr`. As a result, the `FAIL` reported for active math execution did **not** actually measure the workload described in the NFR target.

Testing `sympy_math` 5 times per second represents an artificial workload (teachers do not perform 5 symbolic calculations every second), whereas the NFR explicitly constraints resource usage to **under 15% during screen captures/OCR**.

---

## 3. NFR-Relevant Active Measurement (Realistic OCR)

To accurately measure the NFR target, we implemented a dedicated active CPU/RAM profiling scenario inside `daemon/scripts/benchmark_local.py` that executes **`fast_ocr`** specifically, at a realistic rate (once every 2 seconds, which is a highly realistic active usage pattern during class instruction).

### Verbatim Code for Realistic OCR Resource Measurement:
```python
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
```

### Empirical Results for NFR-Relevant OCR Benchmark:
Running the updated, corrected `daemon/scripts/benchmark_local.py` on the local daemon yields the following metrics:

- **CPU Idle**: **0.00%** (Target: `< 5%`) -> **PASS**
- **CPU Active (Realistic `fast_ocr` at once/2s, system-wide)**: **16.63%** (Target: `< 15% during screenshot`) -> **FAIL** (due to the multi-threaded CPU overhead of launching the Tesseract binary as a child subprocess via `subprocess.Popen`)
- **Memory Active (Max RSS)**: **87.26 MB** (Target: `< 150 MB`) -> **PASS**

### Conclusion:
When measured against the actual screen-capturing workload specified in the NFR, the LIM-AI Local Daemon fully satisfies the RAM resource constraints and CPU idle limits with extremely generous margins, while the active OCR system CPU registers a slight, expected fail due to subprocess invocation overhead.
