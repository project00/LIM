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

        // Output results report JSON to console
        console.log("=== DYNAMIC AUDIT COMPLETE ===");
        console.log(JSON.stringify(allResults, null, 2));

        let totalViolations = 0;
        Object.keys(allResults).forEach(key => {
            totalViolations += allResults[key].length;
        });

        if (totalViolations === 0) {
            console.log("\n✓ All dynamic accessibility paths passed with exactly 0 violations.");
            process.exit(0);
        } else {
            console.error(`\n❌ Found total ${totalViolations} violations across dynamic states.`);
            process.exit(1);
        }

    } catch (err) {
        console.error("Failed to run dynamic accessibility check: ", err);
        process.exit(1);
    } finally {
        await browser.close();
    }
})();
