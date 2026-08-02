#!/usr/bin/env node
/**
 * Regression test for LIM-AI Copilot Widget 3D Model Rendering.
 * Verifies that 3D models served by the local daemon's static models cache mount
 * are successfully fetched and loaded by <model-viewer> inside widget/index.html
 * without any CORS or networking failures.
 * Also asserts that the returned model_url is an ABSOLUTE URL starting with "http://".
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const assert = require('assert');

(async () => {
    console.log("=== Running 3D Model Rendering Regression Test ===");

    // SHA256 of lowercase/trimmed "test_model" is:
    // 7a31e33fa703f3c13795df24d7ca2cbbfb35bf80766dd8d1d8217bf7a18c2267
    const cacheKey = "7a31e33fa703f3c13795df24d7ca2cbbfb35bf80766dd8d1d8217bf7a18c2267";
    const modelDir = path.resolve(__dirname, `../../daemon/model_cache/${cacheKey}`);
    console.log(`Generating self-contained minimal 3D model files at: ${modelDir}`);
    fs.mkdirSync(modelDir, { recursive: true });

    // 1. Write metadata.json
    const metadata = {
        "uid": "test_model_uid",
        "title": "Test Model Title",
        "attribution": {
            "author": "Jules Tester",
            "license": "CC-BY",
            "source_url": "http://localhost"
        }
    };
    fs.writeFileSync(path.join(modelDir, "metadata.json"), JSON.stringify(metadata, null, 2));

    // 2. Write scene.gltf
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

    // 3. Write scene.bin (44 bytes total: 6 bytes indices, 2 bytes padding, 36 bytes vertex positions)
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

    // Back up and prepare temporary config.yaml with an enabled Sketchfab credential to satisfy the Sketchfab guard
    const configPath = path.resolve(__dirname, '../../daemon/config.yaml');
    let originalConfig = '';
    if (fs.existsSync(configPath)) {
        originalConfig = fs.readFileSync(configPath, 'utf8');
    }

    const tempConfig = `
api_key: ''
credentials:
  - id: 'test-sf-id'
    name: 'Test Sketchfab'
    type: 'sketchfab'
    enabled: true
    access_token: 'test-sf-token'
disable_local_backup: false
remote_action_timeout_seconds: 30
remote_base_url: http://192.168.1.100:8000
silence_rms_threshold: 400
`;
    fs.writeFileSync(configPath, tempConfig, 'utf8');
    console.log("Temporary config.yaml with enabled Sketchfab credential successfully written.");

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

        // Listen for WebSocket frame
        const wsPromise = page.waitForEvent('websocket');

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

        // Wait a moment for page initialization and websocket connection
        await page.waitForTimeout(2000);

        const webSocket = await wsPromise;
        console.log("Page WebSocket connected successfully.");

        let receivedAbsoluteUrl = null;
        webSocket.on('framereceived', frame => {
            try {
                const payload = JSON.parse(frame.payload);
                if (payload.type === 'model_3d') {
                    console.log("Captured WS model_3d frame:", payload);
                    receivedAbsoluteUrl = payload.model_url;
                }
            } catch (e) {
                // ignore binary or non-json frames
            }
        });

        console.log("Triggering 3D Model search through UI with query 'test_model'...");
        await page.evaluate(() => {
            toggleInputFlow('model');
            const input = document.getElementById('input-model');
            if (input) {
                input.value = "test_model";
                submitModel();
            }
        });

        // Wait for <model-viewer> to process and load the model
        console.log("Waiting for WS response and <model-viewer> to load...");
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

        // Assert that the WS frame carried an absolute URL
        assert.ok(receivedAbsoluteUrl, "The WebSocket should have returned a 'model_3d' message.");
        assert.ok(receivedAbsoluteUrl.startsWith("http://127.0.0.1:5000/"), `model_url must be an absolute URL pointing to the daemon. Received: ${receivedAbsoluteUrl}`);

        // Assert no failed requests to daemon static assets
        const daemonFailed = failedRequests.filter(r => r.url.includes('/models_cache/'));
        assert.deepStrictEqual(daemonFailed, [], "There should be no failed network requests to the daemon's static models cache mount.");

        // Assert model loaded successfully
        assert.ok(state.loaded, "The <model-viewer> element should have its 'loaded' property set to true.");
        assert.strictEqual(state.src, `http://127.0.0.1:5000/models_cache/${cacheKey}/scene.gltf`, "The <model-viewer> should have its 'src' set correctly to the absolute daemon URL.");

        // Verify CORS headers exist on response
        const gltfResp = responses.find(r => r.url.endsWith('scene.gltf'));
        assert.ok(gltfResp, "Response for scene.gltf should exist.");
        assert.strictEqual(gltfResp.status, 200, "scene.gltf should return 200 OK status.");
        assert.strictEqual(gltfResp.headers['access-control-allow-origin'], '*', "The scene.gltf response must include the 'Access-Control-Allow-Origin: *' header.");

        console.log("✓ Regression test passed successfully!");
        cleanupAndRestore();
        process.exit(0);

    } catch (err) {
        console.error("3D model rendering regression test failed:", err);
        cleanupAndRestore();
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

    function cleanupAndRestore() {
        if (originalConfig) {
            fs.writeFileSync(configPath, originalConfig, 'utf8');
            console.log("Restored original config.yaml.");
        } else if (fs.existsSync(configPath)) {
            fs.unlinkSync(configPath);
            console.log("Removed temporary config.yaml.");
        }
    }
})();
