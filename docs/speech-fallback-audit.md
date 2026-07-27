1. Literal code that starts SpeechRecognition when DEGRADED/OFFLINE + subtitles ON, and stops it when transitioning back to ONLINE (or subtitles are toggled off):

```javascript
        function startLocalSpeechRecognition() {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                const bar = document.getElementById("subtitles-bar");
                if (bar) {
                    bar.innerText = "Sottotitoli non disponibili: browser non supportato";
                }
                return;
            }

            if (recognitionActive) {
                return;
            }

            try {
                recognition = new SpeechRecognition();
                recognition.continuous = true;
                recognition.interimResults = true;
                recognition.lang = 'it-IT';

                recognition.onstart = () => {
                    recognitionActive = true;
                    updateSubtitlesDisplay();
                };

                recognition.onresult = (event) => {
                    let interimTranscript = '';
                    for (let i = event.resultIndex; i < event.results.length; ++i) {
                        const result = event.results[i];
                        if (result.isFinal) {
                            const finalText = result[0].transcript.trim();
                            if (finalText) {
                                handleSubtitleMessage({
                                    type: 'subtitle',
                                    text: finalText,
                                    is_final: true
                                });
                            }
                        } else {
                            interimTranscript += result[0].transcript;
                        }
                    }

                    if (interimTranscript) {
                        handleSubtitleMessage({
                            type: 'subtitle',
                            text: interimTranscript.trim(),
                            is_final: false
                        });
                    } else if (event.results.length > 0 && event.results[event.results.length - 1].isFinal) {
                        interimSubtitle = null;
                        updateSubtitlesDisplay();
                    }
                };

                recognition.onerror = (event) => {
                    console.error("SpeechRecognition error:", event.error);
                };

                recognition.onend = () => {
                    if (recognitionActive && subtitlesActive && (currentState === SYSTEM_STATES.DEGRADED || currentState === SYSTEM_STATES.OFFLINE)) {
                        try {
                            recognition.start();
                        } catch (e) {
                            console.error("Failed to auto-restart SpeechRecognition:", e);
                        }
                    } else {
                        recognitionActive = false;
                        recognition = null;
                    }
                };

                recognitionActive = true;
                recognition.start();
            } catch (err) {
                console.error("Failed to start SpeechRecognition:", err);
                recognitionActive = false;
                recognition = null;
            }
        }
```

```javascript
        function stopLocalSpeechRecognition() {
            recognitionActive = false;
            if (recognition) {
                try {
                    recognition.stop();
                } catch (e) {
                    // Ignore
                }
                recognition = null;
            }
        }
```

```javascript
        function toggleSubtitles() {
            subtitlesActive = !subtitlesActive;
            const btn = document.getElementById("btn-subtitles");
            const bar = document.getElementById("subtitles-bar");
            if (subtitlesActive) {
                btn.style.background = "#a6e3a1"; // Green color
                checkSubtitleConnectionState();
            } else {
                btn.style.background = "#89b4fa"; // Standard button color
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        action: "stop_transcription"
                    }));
                }
                stopLocalSpeechRecognition();
                finalSubtitles = [];
                interimSubtitle = null;
                bar.innerText = "🎙️ Live STT: In attesa di input audio...";
            }
        }

        function checkSubtitleConnectionState() {
            const bar = document.getElementById("subtitles-bar");
            if (!bar) return;
            if (subtitlesActive) {
                if (currentState === SYSTEM_STATES.DEGRADED || currentState === SYSTEM_STATES.OFFLINE) {
                    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                    if (!SpeechRecognition) {
                        bar.innerText = "Sottotitoli non disponibili: browser non supportato";
                    } else {
                        startLocalSpeechRecognition();
                    }
                } else {
                    stopLocalSpeechRecognition();
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({
                            action: "start_transcription",
                            data: { target_language: null }
                        }));
                    }
                    updateSubtitlesDisplay();
                }
            }
        }
```

SpeechRecognition.stop() is called on transition to ONLINE: YES

2. Literal onresult handler:

```javascript
                recognition.onresult = (event) => {
                    let interimTranscript = '';
                    for (let i = event.resultIndex; i < event.results.length; ++i) {
                        const result = event.results[i];
                        if (result.isFinal) {
                            const finalText = result[0].transcript.trim();
                            if (finalText) {
                                handleSubtitleMessage({
                                    type: 'subtitle',
                                    text: finalText,
                                    is_final: true
                                });
                            }
                        } else {
                            interimTranscript += result[0].transcript;
                        }
                    }

                    if (interimTranscript) {
                        handleSubtitleMessage({
                            type: 'subtitle',
                            text: interimTranscript.trim(),
                            is_final: false
                        });
                    } else if (event.results.length > 0 && event.results[event.results.length - 1].isFinal) {
                        interimSubtitle = null;
                        updateSubtitlesDisplay();
                    }
                };
```

Reuses the existing Task 10 rendering function(s) for interim/final subtitles (no duplicated rendering logic): YES

3. Literal code path for browsers without SpeechRecognition support, showing exact string:

```javascript
        function startLocalSpeechRecognition() {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                const bar = document.getElementById("subtitles-bar");
                if (bar) {
                    bar.innerText = "Sottotitoli non disponibili: browser non supportato";
                }
                return;
            }
```

```javascript
        function checkSubtitleConnectionState() {
            const bar = document.getElementById("subtitles-bar");
            if (!bar) return;
            if (subtitlesActive) {
                if (currentState === SYSTEM_STATES.DEGRADED || currentState === SYSTEM_STATES.OFFLINE) {
                    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                    if (!SpeechRecognition) {
                        bar.innerText = "Sottotitoli non disponibili: browser non supportato";
                    } else {
                        startLocalSpeechRecognition();
                    }
                }
```

```javascript
        function updateSubtitlesDisplay() {
            const bar = document.getElementById("subtitles-bar");
            if (!bar) return;

            if (!subtitlesActive) {
                return;
            }

            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if ((currentState === SYSTEM_STATES.DEGRADED || currentState === SYSTEM_STATES.OFFLINE) && !SpeechRecognition) {
                bar.innerText = "Sottotitoli non disponibili: browser non supportato";
                return;
            }
```

4. Literal toast banner call triggered specifically on the DEGRADED/OFFLINE -> ONLINE transition while subtitles are active:

```javascript
            if (subtitlesActive && (oldState === SYSTEM_STATES.DEGRADED || oldState === SYSTEM_STATES.OFFLINE) && newState === SYSTEM_STATES.ONLINE) {
                const toast = document.getElementById("toast-banner");
                toast.innerText = "ℹ️ Sottotitoli: passaggio alla trascrizione cloud";
                toast.style.display = "block";
                setTimeout(() => { toast.style.display = "none"; }, 5000);
            }
```

5. Verification of translation logic in local SpeechRecognition fallback:

No translation logic present in this path: YES

6. Literal tests mocking window.SpeechRecognition:

```javascript
// Test 8: Connection is DEGRADED/OFFLINE while subtitles are active and SpeechRecognition is supported
console.log("Test 8: SpeechRecognition fallback starts in DEGRADED/OFFLINE...");
resetMocks();
context.window.SpeechRecognition = MockSpeechRecognition;
vm.runInContext('subtitlesActive = true', context);
setSystemState(SYSTEM_STATES.DEGRADED, "Local Mode active");

// Ensure MockSpeechRecognition was instantiated and started
const recognitionInstance = MockSpeechRecognition.instance;
assert.notStrictEqual(recognitionInstance, null);
assert.strictEqual(recognitionInstance.started, true);
assert.strictEqual(vm.runInContext('recognitionActive', context), true);

// Trigger a mock SpeechRecognition onresult event
const mockEvent = {
    resultIndex: 0,
    results: [
        {
            isFinal: false,
            0: { transcript: "Buongiorno a tutti" }
        }
    ]
};
recognitionInstance.onresult(mockEvent);
assert.strictEqual(mockElements['subtitles-bar'].innerHTML, '<div><i>Buongiorno a tutti</i></div>');

// Trigger a final result
const mockEventFinal = {
    resultIndex: 0,
    results: [
        {
            isFinal: true,
            0: { transcript: "Buongiorno a tutti" }
        }
    ]
};
recognitionInstance.onresult(mockEventFinal);
assert.strictEqual(mockElements['subtitles-bar'].innerHTML, '<div>Buongiorno a tutti</div>');
console.log("✓ Test 8 Passed");


// Test 9: Transition DEGRADED/OFFLINE -> ONLINE stops SpeechRecognition and shows Cloud banner
console.log("Test 9: Transitioning back to ONLINE stops local STT and displays Toast banner...");
setSystemState(SYSTEM_STATES.ONLINE, "Cloud mode online");

// Ensure recognition was stopped
assert.strictEqual(recognitionInstance.stopped, true);
assert.strictEqual(vm.runInContext('recognitionActive', context), false);

// Check that toast was shown with transition text
assert.strictEqual(mockElements['toast-banner'].innerText, "ℹ️ Sottotitoli: passaggio alla trascrizione cloud");
assert.strictEqual(mockElements['toast-banner'].style.display, "block");
console.log("✓ Test 9 Passed");


// Test 10: If window.SpeechRecognition is not supported, show browser unsupported message
console.log("Test 10: Unsupported browser shows error message...");
resetMocks();
delete context.window.SpeechRecognition;
vm.runInContext('subtitlesActive = true', context);
setSystemState(SYSTEM_STATES.DEGRADED, "Local mode");

assert.strictEqual(mockElements['subtitles-bar'].innerText, "Sottotitoli non disponibili: browser non supportato");
console.log("✓ Test 10 Passed");
```
