# WCAG 1.4.1 Color-Only Indicator Audit

This document audits the quiz verification feedback system in the LIM-AI Local Widget, specifically evaluating compliance with WCAG 2.1 Success Criterion 1.4.1 "Use of Color" (Level A).

---

## 1. Verbatim Original Verification Code

The original DOM and CSS manipulation logic applied when a user clicked the **"Verifica Risposte"** button is implemented inside `renderData` as follows:

```javascript
                    // Verify answers
                    correctIndices.forEach((correctIdx, i) => {
                        const radios = out.querySelectorAll(`input[name="q${i}"]`);
                        let selectedIdx = -1;
                        radios.forEach((radio, rIdx) => {
                            if (radio.checked) {
                                selectedIdx = rIdx;
                            }
                        });

                        radios.forEach((radio, rIdx) => {
                            const lbl = document.getElementById(`quiz-q-${i}-lbl-${rIdx}`);
                            if (!lbl) return;
                            if (rIdx === correctIdx) {
                                // Mark correct option in green
                                lbl.style.backgroundColor = "rgba(166, 227, 161, 0.3)";
                                lbl.style.color = "#a6e3a1";
                                lbl.style.fontWeight = "bold";
                                lbl.style.borderRadius = "4px";
                                lbl.style.padding = "2px 6px";
                                lbl.style.display = "inline-block";
                            } else if (rIdx === selectedIdx) {
                                // Student picked wrong option - mark in red
                                lbl.style.backgroundColor = "rgba(243, 139, 168, 0.3)";
                                lbl.style.color = "#f38ba8";
                                lbl.style.borderRadius = "4px";
                                lbl.style.padding = "2px 6px";
                                lbl.style.display = "inline-block";
                            }
                        });
                    });
```

### Confirmation:
Yes, in the original implementation, correct and incorrect feedback was conveyed **ONLY via color** (green background/text for correct answers, red background/text for wrong selections). Although the correct answer was styled as `bold`, there was no explicit textual indicator, symbol, or glyph (such as "✓" or "✗") to clarify correctness without relying on color perception or font-weight.

---

## 2. WCAG 1.4.1 "Use of Color" (Level A) and Axe-Core Limitations

WCAG Success Criterion 1.4.1 requires that:
> Color is not used as the only visual means of conveying information, indicating an action, prompting a response, or distinguishing a visual element.

This violation was **not** flagged by our automated Playwright + axe-core audits. This is a well-documented limitation of automated accessibility testing tools:
- **Reason**: Axe-core can verify DOM elements, labels, and roles, but it cannot programmatically understand the semantic intent of color changes on arbitrary HTML text nodes. It does not know that green means "correct" and red means "incorrect" in a quiz context. Thus, verifying "Use of Color" remains a manual testing category.

---

## 3. Implemented Fix: Non-Color Indicators

To satisfy WCAG 1.4.1, we updated the verification loop to append explicit textual symbols (**`✓ [Corretto]`** and **`✗ [Scelta errata]`**) next to the checked options. This small, clean enhancement ensures that color-blind, low-vision, or screen-reader users can perceive quiz correctness with absolute certainty.

### Updated Compliant Code:
```javascript
                            if (rIdx === correctIdx) {
                                // Mark correct option in green with checkmark
                                lbl.innerHTML = `✓ ${lbl.innerHTML} <b>[Corretto]</b>`;
                                lbl.style.backgroundColor = "rgba(166, 227, 161, 0.3)";
                                lbl.style.color = "#a6e3a1";
                                lbl.style.fontWeight = "bold";
                                lbl.style.borderRadius = "4px";
                                lbl.style.padding = "2px 6px";
                                lbl.style.display = "inline-block";
                            } else if (rIdx === selectedIdx) {
                                // Student picked wrong option - mark in red with crossmark
                                lbl.innerHTML = `✗ ${lbl.innerHTML} <b>[Scelta errata]</b>`;
                                lbl.style.backgroundColor = "rgba(243, 139, 168, 0.3)";
                                lbl.style.color = "#f38ba8";
                                lbl.style.borderRadius = "4px";
                                lbl.style.padding = "2px 6px";
                                lbl.style.display = "inline-block";
                            }
```
