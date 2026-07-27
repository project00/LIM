const fs = require('fs');
const path = require('path');
const assert = require('assert');
const vm = require('vm');

console.log("=== Running Subtitle System Tests ===");

// 1. Load and parse index.html
const htmlPath = path.join(__dirname, '../index.html');
const htmlContent = fs.readFileSync(htmlPath, 'utf8');

const scriptRegex = /<script>([\s\S]*?)<\/script>/i;
const match = htmlContent.match(scriptRegex);
if (!match) {
    throw new Error("Could not find <script> tag in index.html");
}
const scriptCode = match[1];

// 2. Prepare mock browser environment
const mockElements = {
    'subtitles-bar': {
        innerText: '',
        innerHTML: '',
        scrollTop: 0,
        scrollHeight: 100
    },
    'btn-subtitles': {
        style: { background: '' }
    },
    'status-badge': {
        className: '',
        innerText: ''
    },
    'toast-banner': {
        innerText: '',
        style: { display: '' }
    }
};

const querySelectors = {
    '.remote-only': []
};

const documentMock = {
    getElementById: (id) => {
        if (!mockElements[id]) {
            mockElements[id] = { innerText: '', innerHTML: '', style: {} };
        }
        return mockElements[id];
    },
    querySelectorAll: (selector) => {
        return querySelectors[selector] || [];
    },
    body: {
        classList: {
            toggle: (className) => {}
        }
    }
};

// Mock WebSocket
class MockWebSocket {
    constructor(url) {
        this.url = url;
        MockWebSocket.instances.push(this);
        this.sentMessages = [];
        this.readyState = 1; // OPEN (so we can send messages immediately)
    }
    send(msg) {
        this.sentMessages.push(JSON.parse(msg));
    }
}
MockWebSocket.instances = [];
MockWebSocket.OPEN = 1;

// Mock mermaid
const mermaidMock = {
    initialize: () => {},
    run: () => {}
};

// Mock setInterval
const mockSetInterval = () => {};

let lastTimeoutFn = null;

// Mock SpeechRecognition Class
class MockSpeechRecognition {
    constructor() {
        MockSpeechRecognition.instance = this;
        this.continuous = false;
        this.interimResults = false;
        this.lang = '';
        this.started = false;
        this.stopped = false;
    }
    start() {
        this.started = true;
        if (this.onstart) this.onstart();
    }
    stop() {
        this.stopped = true;
        if (this.onend) this.onend();
    }
}
MockSpeechRecognition.instance = null;

// Create an evaluation context
const context = {
    document: documentMock,
    WebSocket: MockWebSocket,
    mermaid: mermaidMock,
    setInterval: mockSetInterval,
    setTimeout: (fn, delay) => {
        if (delay < 100) {
            fn();
        } else {
            lastTimeoutFn = fn;
        }
    },
    console: console,
    window: {
        SpeechRecognition: MockSpeechRecognition
    }
};

// Run script in the context
vm.createContext(context);
vm.runInContext(scriptCode, context);

// Retrieve functions and state variables from context using VM run
const toggleSubtitles = vm.runInContext('toggleSubtitles', context);
const handleSubtitleMessage = vm.runInContext('handleSubtitleMessage', context);
const updateSubtitlesDisplay = vm.runInContext('updateSubtitlesDisplay', context);
const checkSubtitleConnectionState = vm.runInContext('checkSubtitleConnectionState', context);
const setSystemState = vm.runInContext('setSystemState', context);
const SYSTEM_STATES = vm.runInContext('SYSTEM_STATES', context);

// --- Test Cases ---

function resetMocks() {
    mockElements['subtitles-bar'].innerText = '';
    mockElements['subtitles-bar'].innerHTML = '';
    mockElements['subtitles-bar'].scrollTop = 0;
    mockElements['btn-subtitles'].style.background = '';
    mockElements['toast-banner'].innerText = '';
    mockElements['toast-banner'].style.display = 'none';
    lastTimeoutFn = null;

    // Clear final subtitles and interim subtitles inside context
    vm.runInContext('finalSubtitles = []', context);
    vm.runInContext('interimSubtitle = null', context);
    vm.runInContext('subtitlesActive = false', context);
    vm.runInContext('currentState = SYSTEM_STATES.ONLINE', context);

    const wsInstance = vm.runInContext('ws', context);
    if (wsInstance) {
        wsInstance.sentMessages = [];
    }
}

// Test 1: Turning subtitles ON sends start_transcription
console.log("Test 1: Turning subtitles ON...");
resetMocks();
toggleSubtitles();
assert.strictEqual(vm.runInContext('subtitlesActive', context), true);
assert.strictEqual(mockElements['btn-subtitles'].style.background, '#a6e3a1');
const ws1 = vm.runInContext('ws', context);
assert.strictEqual(ws1.sentMessages.length, 1);
assert.deepStrictEqual(ws1.sentMessages[0], {
    action: 'start_transcription',
    data: { target_language: null }
});
console.log("✓ Test 1 Passed");

// Test 2: Turning subtitles OFF sends stop_transcription
console.log("Test 2: Turning subtitles OFF...");
toggleSubtitles(); // toggle again to turn off
assert.strictEqual(vm.runInContext('subtitlesActive', context), false);
assert.strictEqual(mockElements['btn-subtitles'].style.background, '#89b4fa');
const ws2 = vm.runInContext('ws', context);
assert.strictEqual(ws2.sentMessages.length, 2);
assert.deepStrictEqual(ws2.sentMessages[1], {
    action: 'stop_transcription'
});
assert.strictEqual(mockElements['subtitles-bar'].innerText, "🎙️ Live STT: In attesa di input audio...");
console.log("✓ Test 2 Passed");

// Test 3: is_final=false (interim subtitle result) rendering
console.log("Test 3: Interim subtitle rendering (is_final=false)...");
resetMocks();
vm.runInContext('subtitlesActive = true', context);
handleSubtitleMessage({
    type: 'subtitle',
    text: 'Hello world',
    is_final: false
});
assert.strictEqual(mockElements['subtitles-bar'].innerHTML, '<div><i>Hello world</i></div>');
console.log("✓ Test 3 Passed");

// Test 4: is_final=false replaced by the next interim message
console.log("Test 4: Next interim replaces previous interim...");
handleSubtitleMessage({
    type: 'subtitle',
    text: 'Hello world, how are you',
    is_final: false
});
assert.strictEqual(mockElements['subtitles-bar'].innerHTML, '<div><i>Hello world, how are you</i></div>');
console.log("✓ Test 4 Passed");

// Test 5: is_final=true commits the subtitle permanently and clears interim
console.log("Test 5: Committing subtitle (is_final=true)...");
handleSubtitleMessage({
    type: 'subtitle',
    text: 'Hello world, how are you',
    is_final: true
});
assert.strictEqual(mockElements['subtitles-bar'].innerHTML, '<div>Hello world, how are you</div>');
assert.strictEqual(vm.runInContext('interimSubtitle', context), null);
console.log("✓ Test 5 Passed");

// Test 6: Second subtitle accumulates and doesn't overwrite first
console.log("Test 6: Multiple final subtitles accumulate...");
handleSubtitleMessage({
    type: 'subtitle',
    text: 'I am doing great',
    is_final: true
});
assert.strictEqual(mockElements['subtitles-bar'].innerHTML, '<div>Hello world, how are you</div><div>I am doing great</div>');
console.log("✓ Test 6 Passed");

// Test 7: Translated text is shown alongside original text
console.log("Test 7: Translated text rendering...");
resetMocks();
vm.runInContext('subtitlesActive = true', context);
handleSubtitleMessage({
    type: 'subtitle',
    text: 'Buongiorno',
    translated_text: 'Good morning',
    is_final: false
});
assert.strictEqual(mockElements['subtitles-bar'].innerHTML, '<div><i>Buongiorno (Good morning)</i></div>');

handleSubtitleMessage({
    type: 'subtitle',
    text: 'Buongiorno',
    translated_text: 'Good morning',
    is_final: true
});
assert.strictEqual(mockElements['subtitles-bar'].innerHTML, '<div>Buongiorno (Good morning)</div>');
console.log("✓ Test 7 Passed");

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

console.log("\n=== ALL TESTS PASSED SUCCESSFULLY ===");
process.exit(0);
