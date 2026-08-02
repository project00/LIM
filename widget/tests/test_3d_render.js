#!/usr/bin/env node
/**
 * Regression test for LIM-AI Copilot Widget 3D Model Rendering.
 * Verifies that 3D models served by the local daemon's static models cache mount
 * are successfully fetched and loaded by <model-viewer> inside widget/index.html
 * without any CORS or networking failures.
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const assert = require('assert');

(async () => {
    console.log("=== Running 3D Model Rendering Regression Test ===");

    // Dynamically generate the minimal test model to be completely self-contained and robust against external cleanups
    const modelDir = path.resolve(__dirname, '../../daemon/model_cache/test_model');
    console.log(`Generating self-contained minimal 3D model files at: ${modelDir}`);
    fs.mkdirSync(modelDir, { recursive: true });

    // 1. Write scene.gltf
    const gltfContent = {
        "asset": {
            "version": "2.0"
        },
        "scenes": [
            {
                "nodes": [0]
            }
        ],
        "nodes": [
            {
                "mesh": 0
            }
        ],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 1
                        },
                        "indices": 0
                    }
                ]
            }
        ],
        "buffers": [
            {
                "uri": "scene.bin",
                "byteLength": 44
            }
        ],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": 0,
                "byteLength": 6,
                "target": 34963
            },
            {
                "buffer": 0,
                "byteOffset": 8,
                "byteLength": 36,
                "target": 34962
            }
        ],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5123,
                "count": 3,
                "type": "SCALAR",
                "max": [2],
                "min": [0]
            },
            {
                "bufferView": 1,
                "byteOffset": 0,
                "componentType": 5126,
                "count": 3,
                "type": "VEC3",
                "max": [1.0, 1.0, 0.0],
                "min": [0.0, 0.0, 0.0]
            }
        ]
    };
    fs.writeFileSync(path.join(modelDir, "scene.gltf"), JSON.stringify(gltfContent, null, 2));

    // 2. Write scene.bin (44 bytes total: 6 bytes indices, 2 bytes padding, 36 bytes vertex positions)
    const indices = Buffer.alloc(6);
    indices.writeUInt16LE(0, 0);
    indices.writeUInt16LE(1, 2);
    indices.writeUInt16LE(2, 4);

    const padding = Buffer.alloc(2);

    const positions = Buffer.alloc(36);
    positions.writeFloatLE(0.0, 0);
    positions.writeFloatLE(0.0, 4);
    positions.writeFloatLE(0.0, 8);

    positions.writeFloatLE(1.0, 12);
    positions.writeFloatLE(0.0, 16);
    positions.writeFloatLE(0.0, 20);

    positions.writeFloatLE(0.0, 24);
    positions.writeFloatLE(1.0, 28);
    positions.writeFloatLE(0.0, 32);

    const binData = Buffer.concat([indices, padding, positions]);
    fs.writeFileSync(path.join(modelDir, "scene.bin"), binData);
    console.log("3D model files successfully generated.");

    let daemon;
    let browser;
    try {
        console.log("Starting python daemon...");
        // Kill anything on port 5000 to avoid "port in use" issues
        const killer = spawn('sh', ['-c', 'kill $(lsof -t -i :5000) 2>/dev/null || true']);
        await new Promise(resolve => killer.on('close', resolve));

        const daemonCwd = path.resolve(__dirname, '../../daemon');
        console.log(`Using daemon CWD: ${daemonCwd}`);

        daemon = spawn('poetry', ['run', 'python', 'local_bridge.py'], {
            cwd: daemonCwd,
            env: { ...process.env, PYTHONUNBUFFERED: '1' }
        });

        // Capture daemon output
        daemon.stdout.on('data', (data) => {
            console.log(`[Daemon STDOUT] ${data.toString().trim()}`);
        });
        daemon.stderr.on('data', (data) => {
            console.error(`[Daemon STDERR] ${data.toString().trim()}`);
        });

        // Wait 6 seconds for the daemon to start and begin listening
        await new Promise(resolve => setTimeout(resolve, 6000));

        console.log("Launching Playwright...");
        browser = await chromium.launch({ headless: true });
        const context = await browser.newContext();
        const page = await context.newPage();

        const failedRequests = [];
        const responses = [];

        // Track failed network requests
        page.on('requestfailed', request => {
            const url = request.url();
            const errorText = request.failure() ? request.failure().errorText : 'Unknown';
            failedRequests.push({ url, errorText });
            console.error(`  - Failed network request: ${url} (${errorText})`);
        });

        // Track all network responses
        page.on('response', response => {
            responses.push({
                url: response.url(),
                status: response.status(),
                headers: response.headers()
            });
        });

        const fileUrl = 'file://' + path.resolve(__dirname, '../index.html');
        console.log(`Navigating to ${fileUrl}`);
        await page.goto(fileUrl);

        // Wait a moment for page initialization
        await page.waitForTimeout(1000);

        console.log("Invoking renderData() with cached 3D model...");
        await page.evaluate(() => {
            renderData({
                type: "model_3d",
                model_url: "http://127.0.0.1:5000/models_cache/test_model/scene.gltf",
                label: "Regression Test Model",
                attribution: {
                    author: "Jules Tester",
                    license: "CC-BY",
                    source_url: "http://localhost"
                }
            });
        });

        // Wait for <model-viewer> to load
        console.log("Waiting for <model-viewer> to load the model...");
        await page.waitForTimeout(5000);

        // Retrieve <model-viewer> loading state
        const state = await page.evaluate(() => {
            const mv = document.querySelector('model-viewer');
            if (!mv) return { error: "No <model-viewer> element found" };
            return {
                loaded: mv.loaded,
                src: mv.src
            };
        });

        console.log("Evaluated <model-viewer> state:", state);

        // Assert no failed requests to daemon static assets
        const daemonFailed = failedRequests.filter(r => r.url.includes('/models_cache/'));
        assert.deepStrictEqual(daemonFailed, [], "There should be no failed network requests to the daemon's static models cache mount.");

        // Assert model loaded successfully
        assert.ok(state.loaded, "The <model-viewer> element should have its 'loaded' property set to true.");
        assert.strictEqual(state.src, "http://127.0.0.1:5000/models_cache/test_model/scene.gltf", "The <model-viewer> should have its 'src' set correctly.");

        // Verify CORS headers exist on response
        const gltfResp = responses.find(r => r.url.endsWith('scene.gltf'));
        assert.ok(gltfResp, "Response for scene.gltf should exist.");
        assert.strictEqual(gltfResp.status, 200, "scene.gltf should return 200 OK status.");
        assert.strictEqual(gltfResp.headers['access-control-allow-origin'], '*', "The scene.gltf response must include the 'Access-Control-Allow-Origin: *' header.");

        console.log("✓ Regression test passed successfully!");
        process.exit(0);

    } catch (err) {
        console.error("3D model rendering regression test failed:", err);
        process.exit(1);
    } finally {
        if (browser) {
            await browser.close();
        }
        if (daemon) {
            console.log("Stopping python daemon...");
            daemon.kill('SIGTERM');
        }
    }
})();
