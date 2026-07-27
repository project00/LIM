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
    },
    'subtitle-language': {
        value: '',
        disabled: false
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
    },
    createElement: (tagName) => {
        return {
            id: '',
            style: {},
            innerText: '',
            onclick: null
        };
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

// Mock Plotly
const MockPlotly = {
    newPlots: [],
    purges: [],
    newPlot: function(container, data, layout, config) {
        this.newPlots.push({ container, data, layout, config });
    },
    purge: function(container) {
        this.purges.push(container);
    }
};

// Mock KaTeX
const MockKatex = {
    render: function() {}
};

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
    },
    Plotly: MockPlotly,
    katex: MockKatex
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
    mockElements['subtitle-language'].value = '';
    mockElements['subtitle-language'].disabled = false;
    lastTimeoutFn = null;

    // Clear final subtitles and interim subtitles inside context
    vm.runInContext('finalSubtitles = []', context);
    vm.runInContext('interimSubtitle = null', context);
    vm.runInContext('subtitlesActive = false', context);
    vm.runInContext('currentState = SYSTEM_STATES.ONLINE', context);
    vm.runInContext('lessonLog = []', context);

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

// Test 11: Changing language while subtitles are active sends stop + start immediately
console.log("Test 11: Changing language while subtitles are active restarts the transcription...");
resetMocks();
vm.runInContext('subtitlesActive = true', context);
vm.runInContext('currentState = SYSTEM_STATES.ONLINE', context);
mockElements['subtitle-language'].value = 'en';

const handleLanguageChange = vm.runInContext('handleLanguageChange', context);
handleLanguageChange();

const ws11 = vm.runInContext('ws', context);
assert.strictEqual(ws11.sentMessages.length, 2);
assert.deepStrictEqual(ws11.sentMessages[0], {
    action: 'stop_transcription'
});
assert.deepStrictEqual(ws11.sentMessages[1], {
    action: 'start_transcription',
    data: { target_language: 'en' }
});
console.log("✓ Test 11 Passed");


// Test 12: Select is disabled on DEGRADED/OFFLINE state
console.log("Test 12: Select is disabled in DEGRADED/OFFLINE states...");
resetMocks();
setSystemState(SYSTEM_STATES.DEGRADED, "Local mode");
assert.strictEqual(mockElements['subtitle-language'].disabled, true);

resetMocks();
setSystemState(SYSTEM_STATES.OFFLINE, "Offline mode");
assert.strictEqual(mockElements['subtitle-language'].disabled, true);

resetMocks();
setSystemState(SYSTEM_STATES.ONLINE, "Online mode");
assert.strictEqual(mockElements['subtitle-language'].disabled, false);
console.log("✓ Test 12 Passed");


// Test 14: Math Plotly Rendering Integration
console.log("Test 14: Math Plotly Rendering Integration...");
resetMocks();
const testMathData = {
    type: "math",
    latex: "f(x) = x^2",
    plot_data: {
        x: [-1, 0, 1],
        y: [1, 0, 1]
    }
};

// Clear MockPlotly records
MockPlotly.newPlots = [];
MockPlotly.purges = [];

// Prepare a mock parent container
const mockMathOut = {
    innerHTML: '',
    appendChild: (child) => {
        mockMathOut.appendedChildren = mockMathOut.appendedChildren || [];
        mockMathOut.appendedChildren.push(child);
    }
};

const originalGetElementByIdMath = documentMock.getElementById;
documentMock.getElementById = (id) => {
    if (id === "output") return mockMathOut;
    return originalGetElementByIdMath(id);
};

// Execute renderData
const renderDataMath = vm.runInContext('renderData', context);
renderDataMath(testMathData);

// Verify KaTeX was rendered
assert.notStrictEqual(mockMathOut.appendedChildren, undefined);
assert.strictEqual(mockMathOut.appendedChildren.length, 2); // math-formula and math-chart divs
assert.strictEqual(mockMathOut.appendedChildren[0].id, "math-formula");
assert.strictEqual(mockMathOut.appendedChildren[1].id, "math-chart");

// Verify Plotly was called
assert.strictEqual(MockPlotly.newPlots.length, 1);
assert.strictEqual(MockPlotly.purges.length, 1);
assert.deepStrictEqual(MockPlotly.newPlots[0].data[0].x, [-1, 0, 1]);
assert.deepStrictEqual(MockPlotly.newPlots[0].data[0].y, [1, 0, 1]);
assert.strictEqual(MockPlotly.newPlots[0].config.responsive, true);
assert.strictEqual(MockPlotly.newPlots[0].config.scrollZoom, true);

// Restore original stub
documentMock.getElementById = originalGetElementByIdMath;
console.log("✓ Test 14 Passed");


// Test 15: 3D Model Attribution Rendering
console.log("Test 15: 3D Model Attribution Rendering...");
resetMocks();
const testModelData = {
    type: "model_3d",
    model_url: "/models/123/scene.gltf",
    label: "Earth Model",
    attribution: {
        author: "NASA Science",
        license: "CC-BY-4.0",
        source_url: "https://sketchfab.com/earth"
    }
};

const mockModelOut = {
    innerHTML: ''
};

const originalGetElementByIdModel = documentMock.getElementById;
documentMock.getElementById = (id) => {
    if (id === "output") return mockModelOut;
    return originalGetElementByIdModel(id);
};

// Execute renderData
const renderDataModel = vm.runInContext('renderData', context);
renderDataModel(testModelData);

// Assert the innerHTML contains <model-viewer> and CC attribution link, author, and license
assert.ok(mockModelOut.innerHTML.includes("<model-viewer"));
assert.ok(mockModelOut.innerHTML.includes("NASA Science"));
assert.ok(mockModelOut.innerHTML.includes("CC-BY-4.0"));
assert.ok(mockModelOut.innerHTML.includes('href="https://sketchfab.com/earth"'));
assert.ok(mockModelOut.innerHTML.includes("Earth Model"));

// Restore original stub
documentMock.getElementById = originalGetElementByIdModel;
console.log("✓ Test 15 Passed");


// Test 13: Interactive Quiz Verification
console.log("Test 13: Interactive Quiz Verification...");
resetMocks();
const renderData = vm.runInContext('renderData', context);
const testQuizData = {
    type: "quiz",
    questions: [
        {
            question: "What is 2+2?",
            options: ["3", "4", "5"],
            correct_index: 1
        }
    ]
};

// Mock output container
const mockOutputElement = {
    innerHTML: '',
    querySelectorAll: (selector) => {
        // We'll return mock objects for inputs
        if (selector === "input[type='radio']") {
            return mockRadios;
        }
        if (selector === 'input[name="q0"]') {
            return mockRadios;
        }
        return [];
    },
    appendChild: (child) => {
        mockOutputElement.appendedChild = child;
    }
};

const mockRadios = [
    { checked: false, disabled: false },
    { checked: true, disabled: false },
    { checked: false, disabled: false }
];

const mockLabels = [
    { id: 'quiz-q-0-lbl-0', style: {} },
    { id: 'quiz-q-0-lbl-1', style: {} },
    { id: 'quiz-q-0-lbl-2', style: {} }
];

// Stub document.getElementById to return our labels and output element
const originalGetElementById = documentMock.getElementById;
documentMock.getElementById = (id) => {
    if (id === "output") return mockOutputElement;
    if (id.startsWith("quiz-q-0-lbl-")) {
        const idx = parseInt(id.split("-").pop());
        return mockLabels[idx];
    }
    return originalGetElementById(id);
};

renderData(testQuizData);

// Assert the quiz verification button was created and appended
assert.notStrictEqual(mockOutputElement.appendedChild, undefined);
assert.strictEqual(mockOutputElement.appendedChild.id, "btn-verify-quiz");

// Trigger verification click
mockOutputElement.appendedChild.onclick();

// Assert inputs are disabled
mockRadios.forEach(r => assert.strictEqual(r.disabled, true));
assert.strictEqual(mockOutputElement.appendedChild.disabled, true);

// Assert correct option is marked green (index 1 is correct)
assert.strictEqual(mockLabels[1].style.backgroundColor, "rgba(166, 227, 161, 0.3)");
assert.strictEqual(mockLabels[1].style.color, "#a6e3a1");

// Restore original stub
documentMock.getElementById = originalGetElementById;
console.log("✓ Test 13 Passed");


// Test 16: lessonLog Accumulation
console.log("Test 16: lessonLog Accumulation...");
resetMocks();

const mockLogOut = {
    innerHTML: '',
    appendChild: (child) => {
        mockLogOut.appendedChildren = mockLogOut.appendedChildren || [];
        mockLogOut.appendedChildren.push(child);
    },
    querySelectorAll: (selector) => {
        return [];
    }
};

const originalGetElementByIdLog = documentMock.getElementById;
documentMock.getElementById = (id) => {
    if (id === "output") return mockLogOut;
    return originalGetElementByIdLog(id);
};

// 1. Log subtitle (is_final === true)
vm.runInContext('subtitlesActive = true', context);
handleSubtitleMessage({
    type: 'subtitle',
    text: 'Buongiorno a tutti',
    is_final: true
});

// 2. Log math render
const testMathLog = {
    type: "math",
    latex: "f(x) = x^2"
};
const renderDataLog = vm.runInContext('renderData', context);
renderDataLog(testMathLog);

// 3. Log concept_map render
const testConceptLog = {
    type: "concept_map",
    mermaid_code: "graph TD; A-->B"
};
renderDataLog(testConceptLog);

// 4. Log quiz render
const testQuizLog = {
    type: "quiz",
    questions: [
        { question: "Domanda 1", options: ["A", "B"], correct_index: 0 }
    ]
};
renderDataLog(testQuizLog);

documentMock.getElementById = originalGetElementByIdLog;

// Verify lessonLog entries inside VM
const currentLog = vm.runInContext('lessonLog', context);
assert.strictEqual(currentLog.length, 4);

assert.strictEqual(currentLog[0].type, 'subtitle');
assert.strictEqual(currentLog[0].content, 'Buongiorno a tutti');
assert.ok(currentLog[0].timestamp);

assert.strictEqual(currentLog[1].type, 'math');
assert.strictEqual(currentLog[1].content, 'Espressione matematica: f(x) = x^2');
assert.ok(currentLog[1].timestamp);

assert.strictEqual(currentLog[2].type, 'concept_map');
assert.strictEqual(currentLog[2].content, 'Mappa concettuale: graph TD; A-->B');
assert.ok(currentLog[2].timestamp);

assert.strictEqual(currentLog[3].type, 'quiz');
assert.strictEqual(currentLog[3].content, 'Quiz: Domanda 1');
assert.ok(currentLog[3].timestamp);

console.log("✓ Test 16 Passed");


// Test 17: triggerSummary empty lessonLog toast
console.log("Test 17: triggerSummary empty lessonLog toast...");
resetMocks();

const triggerSummary = vm.runInContext('triggerSummary', context);
triggerSummary();

// Verify toast banner displays the correct error message
assert.strictEqual(mockElements['toast-banner'].innerText, "Nessun contenuto da riassumere ancora");
assert.strictEqual(mockElements['toast-banner'].style.display, "block");
console.log("✓ Test 17 Passed");


// Test 18: triggerSummary successful WebSocket message
console.log("Test 18: triggerSummary successful WebSocket message...");
resetMocks();

// Populate log first
vm.runInContext('subtitlesActive = true', context);
handleSubtitleMessage({
    type: 'subtitle',
    text: 'Buongiorno a tutti',
    is_final: true
});

const ws18 = vm.runInContext('ws', context);
assert.strictEqual(ws18.sentMessages.length, 0); // we reset sentMessages in resetMocks

const triggerSummary18 = vm.runInContext('triggerSummary', context);
triggerSummary18();

// Check if WebSocket sent the generate_summary action with log data
assert.strictEqual(ws18.sentMessages.length, 1);
const msg = ws18.sentMessages[0];
assert.strictEqual(msg.action, "generate_summary");
assert.strictEqual(msg.data.lesson_log.length, 1);
assert.strictEqual(msg.data.lesson_log[0].content, "Buongiorno a tutti");
console.log("✓ Test 18 Passed");


// Test 19: Summary Rendering
console.log("Test 19: Summary Rendering...");
resetMocks();

const testSummaryData = {
    type: "summary",
    summary: "Paragrafo uno con caratteri speciali <>&.\n\nParagrafo due."
};

const mockSummaryOut = {
    innerHTML: ''
};

const originalGetElementByIdSummary = documentMock.getElementById;
documentMock.getElementById = (id) => {
    if (id === "output") return mockSummaryOut;
    return originalGetElementByIdSummary(id);
};

const renderDataSummary = vm.runInContext('renderData', context);
renderDataSummary(testSummaryData);

// Verify formatting: split by \n\n, wrap each in <p>, and escapeHTML
const expectedHTML = "<p>Paragrafo uno con caratteri speciali &lt;&gt;&amp;.</p><p>Paragrafo due.</p>";
assert.strictEqual(mockSummaryOut.innerHTML, expectedHTML);

documentMock.getElementById = originalGetElementByIdSummary;
console.log("✓ Test 19 Passed");


console.log("\n=== ALL TESTS PASSED SUCCESSFULLY ===");
process.exit(0);
