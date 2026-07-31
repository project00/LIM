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
