# LIM-AI Copilot Widget Accessibility Audit Report

This report documents the automated accessibility auditing results and fixes performed on the LIM-AI Copilot Widget, as specified in the **docs/project-plan.md** (§10) and Sprint 7 goals.

The audit was executed in the sandbox environment on July 30, 2026, using **Playwright** and **axe-core** (`@axe-core/playwright`) against WCAG 2.1 AA rules.

---

## 1. Initial Accessibility Findings

The initial automated scan reported **4 distinct accessibility violations** present across both default and DSA modes:

| ID | Description / Rule | Impact | Target DOM Element |
| :--- | :--- | :--- | :--- |
| **`landmark-one-main`** | Document should have exactly one main landmark | Moderate | `html` |
| **`page-has-heading-one`** | Page should contain a level-one heading (`<h1>`) | Moderate | `html` |
| **`region`** | All page content should be contained by landmarks | Moderate | `.header`, `#toast-banner`, `#subtitles-bar`, `#subtitle-language`, `#output-container` |
| **`select-name`** | Select element must have an accessible name | Critical | `select#subtitle-language` |

---

## 2. Implemented Accessibility Fixes

To achieve full compliance with WCAG 2.1 AA, the following structural and ARIA enhancements were implemented in `widget/index.html`:

1. **Semantic Landmarks (`landmark-one-main`, `region`)**:
   - Wrapped the entire main output/input container inside a `<main id="main-content">` tag.
   - Wrapped the heading, toast banners, and toolbars inside a semantic `<header>` region.
   - This ensures all content is parsed within standard accessibility landmarks, allowing screen readers to skip directly to relevant sections.

2. **Page Heading (`page-has-heading-one`)**:
   - Replaced the generic `<span>AI LIM Copilot</span>` in the header with a semantic `<h1>` element (`<h1 style="font-weight:bold; font-size:14px; margin: 0;">AI LIM Copilot</h1>`).

3. **Accessible Labels (`select-name`)**:
   - Added `aria-label="Lingua dei sottotitoli"` to the `select#subtitle-language` dropdown.
   - Added `aria-label="Inserisci Espressione Matematica"`, `aria-label="Argomento della Mappa"`, and `aria-label="Nome Modello 3D"` to the respective text `<input>` fields in `#inputs-area`.
   - Added `aria-label` tags to the radio options generated during interactive quiz renderings.

4. **Live Region Attributes (`subtitles-bar`)**:
   - Explicitly added **`aria-live="polite" role="status" aria-atomic="false"`** to the `#subtitles-bar` subtitle output block.
   - This ensures that when a new subtitle chunk is transcribed or translated, screen readers automatically announce the new text politely to deaf/hard-of-hearing students without interrupting active selections or navigation.

---

## 3. Post-Fix Verification

Following the implementations, the automated Playwright regression suite was re-run:

- **Scan 1: Default State**: **0 Violations found** -> **PASS**
- **Scan 2: DSA Mode State**: **0 Violations found** -> **PASS**

Color contrast checks for the dark theme (`#1e1e2e` background and `#cdd6f4` text/badge colors) passed successfully under WCAG 2.1 AA's 4.5:1 minimum contrast criteria.

---

## 4. Audit Scope & Verification Limitations

While the automated Playwright + axe-core suite confirms complete compliance regarding DOM structure and ARIA validation, it is critical to document the boundaries of automated testing:

- **Structural vs. Behavioral**: Axe-core evaluates structural markup, label presence, and semantic validity. It **cannot** verify the exact acoustic or focus rendering of active screen reader software (such as NVDA, JAWS, or VoiceOver).
- **Manual Verification Debt**: Complete and final user-experience validation requires a manual pass with actual screen readers operated by a human user (simulating focus navigation and speech synthesis). This is cataloged as a hardware-dependent manual testing step, mirroring the SpeechRecognition/micro-capture verification Category.
