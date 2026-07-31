# LIM-AI Copilot Widget Accessibility Audit Report

This report documents the automated accessibility auditing results, structural fixes, and dynamic DOM regression tests performed on the LIM-AI Copilot Widget, as specified in the **docs/project-plan.md** (§10) and Sprint 7 goals.

The audits were executed in the sandbox environment on July 30, 2026, using **Playwright** and **axe-core** (`@axe-core/playwright`) against WCAG 2.1 AA rules.

---

## 1. Initial Empty-State Accessibility Audit (Confirmation)

The original accessibility scan executed on the widget loaded `widget/index.html` and audited it **only in its initial/empty state**, without rendering any dynamic content or mock messages first.

### Literal Playwright Test Code of the Original Scan:
```javascript
#!/usr/bin/env node
/**
 * Automated accessibility regression test for LIM-AI Copilot Widget.
 * Loads widget/index.html in headless Chromium and runs axe-core scans
 * against both default and DSA modes.
 */

const { chromium } = require('playwright');
const AxeBuilder = require('@axe-core/playwright').default;
const path = require('path');
const assert = require('assert');

(async () => {
    console.log("=== Running Widget Accessibility Regression Tests ===");

    let browser;
    try {
        browser = await chromium.launch({ headless: true });
        const context = await browser.newContext();
        const page = await context.newPage();

        const fileUrl = 'file://' + path.resolve(__dirname, '../index.html');
        await page.goto(fileUrl);

        // 1. Scan default state
        console.log("Scan 1: Default State...");
        const resultsDefault = await new AxeBuilder({ page }).analyze();
        const defaultViolationsCount = resultsDefault.violations.length;
        console.log(`  Violations found: ${defaultViolationsCount}`);

        if (defaultViolationsCount > 0) {
            console.error("Accessibility violations found in Default State:");
            resultsDefault.violations.forEach(v => {
                console.error(`  - [${v.id}] ${v.help} (${v.impact})`);
                v.nodes.forEach(n => console.error(`      Target: ${n.target}`));
            });
        }
        assert.strictEqual(defaultViolationsCount, 0, "Default state should have exactly 0 accessibility violations.");
        console.log("✓ Default State accessibility audit passed.");

        // 2. Toggle DSA mode
        console.log("Scan 2: Toggling DSA Mode...");
        await page.evaluate(() => {
            toggleDSA();
        });

        const resultsDSA = await new AxeBuilder({ page }).analyze();
        const dsaViolationsCount = resultsDSA.violations.length;
        console.log(`  Violations found: ${dsaViolationsCount}`);

        if (dsaViolationsCount > 0) {
            console.error("Accessibility violations found in DSA Mode:");
            resultsDSA.violations.forEach(v => {
                console.error(`  - [${v.id}] ${v.help} (${v.impact})`);
                v.nodes.forEach(n => console.error(`      Target: ${n.target}`));
            });
        }
        assert.strictEqual(dsaViolationsCount, 0, "DSA Mode should have exactly 0 accessibility violations.");
        console.log("✓ DSA Mode accessibility audit passed.");

        console.log("=== ALL ACCESSIBILITY TESTS PASSED SUCCESSFULLY ===");
        process.exit(0);

    } catch (err) {
        console.error("Accessibility test suite failed: ", err);
        process.exit(1);
    } finally {
        if (browser) {
            await browser.close();
        }
    }
})();
```

---

## 2. Implemented Accessibility Fixes

To achieve full compliance with WCAG 2.1 AA in both empty and dynamic states, the following semantic and ARIA enhancements were implemented in `widget/index.html`:

1. **Semantic Landmarks**:
   - Wrapped the entire main output and input flow container inside a `<main id="main-content">` tag.
   - Wrapped the heading, toast banners, and toolbars inside a semantic `<header>` region.

2. **Page Heading**:
   - Replaced the generic `<span>AI LIM Copilot</span>` in the header with a semantic `<h1>` element.

3. **Accessible Labels**:
   - Added `aria-label="Lingua dei sottotitoli"` to the `select#subtitle-language` dropdown.
   - Added `aria-label="Inserisci Espressione Matematica"`, `aria-label="Argomento della Mappa"`, and `aria-label="Nome Modello 3D"` to the respective text `<input>` fields in `#inputs-area`.
   - Added `aria-label` tags to the radio options generated during interactive quiz renderings.

4. **Live Region Attributes (`subtitles-bar`)**:
   - Explicitly added **`aria-live="polite" role="status" aria-atomic="false"`** to the `#subtitles-bar` subtitle output block.
   - This ensures that when a new subtitle chunk is transcribed or translated, screen readers automatically announce the new text politely to deaf/hard-of-hearing students without interrupting active selections or navigation.

5. **Non-Color Indicators (Quiz Verification)**:
   - Appended non-color glyphs (`✓` and `✗`) alongside explicit textual labels (`[Corretto]` and `[Scelta errata]`) to correct/incorrect option labels on quiz verification, meeting WCAG 1.4.1 Success Criterion (Level A).

---

## 3. Dynamic States Accessibility Audits (Playwright + Axe-Core)

To ensure that the accessibility properties remain intact when dynamic elements are rendered in the DOM, we created `widget/tests/test_accessibility_dynamic.js`. This script populates the page with realistic EdTech mock payloads via `renderData(data)` and audits each state independently under both default and DSA modes.

### Literal Playwright Code for the Dynamic Scans:
```javascript
#!/usr/bin/env node
/**
 * Automated dynamic accessibility check for LIM-AI Copilot Widget.
 * Exercises all dynamic DOM paths (renderData calls) before scanning with axe-core.
 */

const { chromium } = require('playwright');
const AxeBuilder = require('@axe-core/playwright').default;
const path = require('path');
const assert = require('assert');

// Mock data definitions
const mockMessages = {
    math: {
        type: "math",
        latex: "f(x) = x^2 - 4",
        plot_data: {
            x: [-2, -1, 0, 1, 2],
            y: [0, -3, -4, -3, 0]
        }
    },
    concept_map: {
        type: "concept_map",
        mermaid_code: "graph TD\n  A[Apparato Circolatorio] --> B[Cuore]\n  A --> C[Vasi Sanguigni]"
    },
    quiz: {
        type: "quiz",
        questions: [
            {
                question: "Quale organo pompa il sangue?",
                options: ["Polmoni", "Cuore", "Cervello", "Fegato"],
                correct_index: 1
            }
        ]
    },
    model_3d: {
        type: "model_3d",
        model_url: "/models_cache/test_model/scene.gltf",
        label: "Modello Didattico Cuore",
        attribution: {
            author: "EdTech Bio Solutions",
            license: "CC-BY-4.0",
            source_url: "https://sketchfab.com/anatomy-heart"
        }
    },
    subtitle_final: {
        type: "subtitle",
        text: "Benvenuti alla lezione di oggi.",
        is_final: true
    },
    subtitle_interim: {
        type: "subtitle",
        text: "Inizieremo parlando dell",
        is_final: false
    }
};

async function runScan(page, stateName, isDsa = false) {
    if (isDsa) {
        await page.evaluate(() => {
            if (!document.body.classList.contains("dsa-mode")) {
                toggleDSA();
            }
        });
    } else {
        await page.evaluate(() => {
            if (document.body.classList.contains("dsa-mode")) {
                toggleDSA();
            }
        });
    }

    const results = await new AxeBuilder({ page }).analyze();
    return results.violations;
}

(async () => {
    console.log("=== Running Dynamic Accessibility Scans ===");

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    const fileUrl = 'file://' + path.resolve(__dirname, '../index.html');

    const allResults = {};

    try {
        // --- 1. Empty/Initial State ---
        await page.goto(fileUrl);
        allResults["empty_default"] = await runScan(page, "Empty State (Default)", false);
        allResults["empty_dsa"] = await runScan(page, "Empty State (DSA)", true);

        // --- 2. Math & Plotly ---
        await page.goto(fileUrl);
        await page.evaluate((data) => renderData(data), mockMessages.math);
        allResults["math_default"] = await runScan(page, "Math & Plotly (Default)", false);
        allResults["math_dsa"] = await runScan(page, "Math & Plotly (DSA)", true);

        // --- 3. Concept Map ---
        await page.goto(fileUrl);
        await page.evaluate((data) => renderData(data), mockMessages.concept_map);
        allResults["concept_map_default"] = await runScan(page, "Concept Map (Default)", false);
        allResults["concept_map_dsa"] = await runScan(page, "Concept Map (DSA)", true);

        // --- 4. Quiz (Before verification) ---
        await page.goto(fileUrl);
        await page.evaluate((data) => renderData(data), mockMessages.quiz);
        allResults["quiz_before_default"] = await runScan(page, "Quiz Before Verification (Default)", false);
        allResults["quiz_before_dsa"] = await runScan(page, "Quiz Before Verification (DSA)", true);

        // --- 5. Quiz (After verification) ---
        await page.goto(fileUrl);
        await page.evaluate((data) => {
            renderData(data);
            // Select wrong answer (index 0) to trigger both green/red styling
            const radio = document.querySelector('input[value="0"]');
            if (radio) {
                radio.click();
            }
            // Click verification button
            const btn = document.getElementById("btn-verify-quiz");
            if (btn) {
                btn.click();
            }
        }, mockMessages.quiz);
        allResults["quiz_after_default"] = await runScan(page, "Quiz After Verification (Default)", false);
        allResults["quiz_after_dsa"] = await runScan(page, "Quiz After Verification (DSA)", true);

        // --- 6. 3D Model with Attribution ---
        await page.goto(fileUrl);
        await page.evaluate((data) => renderData(data), mockMessages.model_3d);
        allResults["model_3d_default"] = await runScan(page, "3D Model (Default)", false);
        allResults["model_3d_dsa"] = await runScan(page, "3D Model (DSA)", true);

        // --- 7. Final Subtitle ---
        await page.goto(fileUrl);
        await page.evaluate(() => toggleSubtitles()); // activate subtitles bar listening
        await page.evaluate((data) => handleSubtitleMessage(data), mockMessages.subtitle_final);
        allResults["subtitle_final_default"] = await runScan(page, "Final Subtitle (Default)", false);
        allResults["subtitle_final_dsa"] = await runScan(page, "Final Subtitle (DSA)", true);

        // --- 8. Interim Subtitle ---
        await page.goto(fileUrl);
        await page.evaluate(() => toggleSubtitles()); // activate subtitles bar listening
        await page.evaluate((data) => handleSubtitleMessage(data), mockMessages.subtitle_interim);
        allResults["subtitle_interim_default"] = await runScan(page, "Interim Subtitle (Default)", false);
        allResults["subtitle_interim_dsa"] = await runScan(page, "Interim Subtitle (DSA)", true);
```

---

## 4. Post-Fix Verification & Literal JSON Outputs

Every dynamic and static path evaluated in both Default and DSA modes passed the automated WCAG 2.1 AA regression audit.

Below is the **literal raw axe-core JSON violations output array** for each state, confirming exact compliance:

```json
{
  "empty_default": [],
  "empty_dsa": [],
  "math_default": [],
  "math_dsa": [],
  "concept_map_default": [],
  "concept_map_dsa": [],
  "quiz_before_default": [],
  "quiz_before_dsa": [],
  "quiz_after_default": [],
  "quiz_after_dsa": [],
  "model_3d_default": [],
  "model_3d_dsa": [],
  "subtitle_final_default": [],
  "subtitle_final_dsa": [],
  "subtitle_interim_default": [],
  "subtitle_interim_dsa": []
}
```

### Detailed State Verification Status:
- **Initial/Empty State (Default Mode)**: **PASS** (0 Violations)
- **Initial/Empty State (DSA Mode)**: **PASS** (0 Violations)
- **Math formula & Plotly scatter chart (Default Mode)**: **PASS** (0 Violations)
- **Math formula & Plotly scatter chart (DSA Mode)**: **PASS** (0 Violations)
- **Mermaid-based Concept Map (Default Mode)**: **PASS** (0 Violations)
- **Mermaid-based Concept Map (DSA Mode)**: **PASS** (0 Violations)
- **Interactive Quiz - Before Checking (Default Mode)**: **PASS** (0 Violations)
- **Interactive Quiz - Before Checking (DSA Mode)**: **PASS** (0 Violations)
- **Interactive Quiz - After Checking & Styling (Default Mode)**: **PASS** (0 Violations)
- **Interactive Quiz - After Checking & Styling (DSA Mode)**: **PASS** (0 Violations)
- **3D Model `<model-viewer>` with attribution text/links (Default Mode)**: **PASS** (0 Violations)
- **3D Model `<model-viewer>` with attribution text/links (DSA Mode)**: **PASS** (0 Violations)
- **Live Subtitles - Final result committed (Default Mode)**: **PASS** (0 Violations)
- **Live Subtitles - Final result committed (DSA Mode)**: **PASS** (0 Violations)
- **Live Subtitles - Interim result rendering (Default Mode)**: **PASS** (0 Violations)
- **Live Subtitles - Interim result rendering (DSA Mode)**: **PASS** (0 Violations)

---

## 5. Audit Scope & Verification Limitations

While the automated Playwright + axe-core suite confirms complete compliance regarding DOM structure and ARIA validation across all dynamic pathways, it is critical to document the boundaries of automated testing:

- **Structural vs. Behavioral**: Axe-core evaluates structural HTML markup, label presence, and semantic validity. It **cannot** verify the actual acoustic or focus rendering of active screen reader software (such as NVDA, JAWS, or VoiceOver).
- **Manual Verification Debt**: Complete and final user-experience validation requires a manual pass with actual screen readers operated by a human user (simulating focus navigation and speech synthesis). This is cataloged as a hardware-dependent manual testing step, mirroring the SpeechRecognition/micro-capture verification Category.
- **Manual Success Criterion 1.4.1 (Use of Color)**:
  - Automated tools (axe-core) cannot reliably check whether color is the only indicator of a state change (such as quiz correctness).
  - Therefore, verifying Success Criterion 1.4.1 is tracked as an explicit manual/static review item. Future quiz-related UI modifications must always be visually re-checked by eye to guarantee that correct/incorrect states are never indicated solely by green/red background/text color, but always carry distinct text/symbols (`✓ [Corretto]` or `✗ [Scelta errata]`).
