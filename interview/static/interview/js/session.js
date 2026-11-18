/**
 * PrepForge Session Controller
 * Coordinates question fetching, in-browser reference verification, Monaco setup,
 * test evaluation, and submission lifecycle.
 */

let editorInstance = null;
let currentQuestionData = null;
let sessionTimerInstance = null;

document.addEventListener("DOMContentLoaded", () => {
    initSessionFlow();
});

async function initSessionFlow() {
    const config = window.SESSION_CONFIG;
    if (!config) return;

    try {
        await loadAndVerifyQuestion();
    } catch (err) {
        console.error("Initialization failure:", err);
        showOverlayError("Failed to initialize question: " + err.message);
    }
}

async function loadAndVerifyQuestion(attempt = 1) {
    const config = window.SESSION_CONFIG;
    updateOverlayText(
        `Synthesizing Question ${config.order} of ${config.totalQuestions}...`,
        `Calling Gemini for company-tailored problem specification (Attempt ${attempt}/3)...`
    );

    // 1. Fetch pending question from API
    const response = await fetch(`/api/sessions/${config.sessionId}/next-question/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": config.csrfToken
        }
    });

    if (!response.ok) {
        throw new Error(`Server returned ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    if (data.finished) {
        window.location.href = `/sessions/${config.sessionId}/results/`;
        return;
    }

    currentQuestionData = data;

    // 2. Headline In-Browser Verification Check
    if (data.status === "pending") {
        updateOverlayText(
            `Verifying Question ${config.order}...`,
            `Executing reference solution against ${data.test_cases.length} test cases inside in-browser Web Worker (Pyodide)...`
        );

        const verifyResult = await window.PrepForgeRunner.runTests(
            data.reference_solution,
            data.function_name,
            data.test_cases,
            "verify",
            7000
        );

        const allPassed = verifyResult.results && verifyResult.results.length > 0 &&
                          verifyResult.results.every(r => r.passed === true);

        // Report verification back to Django server
        const verifyResp = await fetch(`/api/questions/${data.question_id}/verify/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": config.csrfToken
            },
            body: JSON.stringify({
                passed: allPassed,
                error_details: allPassed ? null : "Reference solution failed tests or timed out"
            })
        });

        const verifyOutcome = await verifyResp.json();

        if (!allPassed) {
            console.warn("Reference solution rejected! Retrying generation...", verifyResult);
            if (attempt < 3) {
                return await loadAndVerifyQuestion(attempt + 1);
            } else {
                showOverlayError("Could not verify question after 3 attempts. Please retry the slot.");
                return;
            }
        }
    }

    // 3. Question is approved & verified -> Render to UI
    renderProblemUI(data);
    initMonacoEditor(data.starter_code);
    initTimer(data.remaining_seconds);
    hideVerificationOverlay();
}

function renderProblemUI(data) {
    document.getElementById("problemTitle").textContent = data.title;
    document.getElementById("problemTopic").textContent = `Topic: ${data.topic}`;
    document.getElementById("problemDescription").textContent = data.description;
    document.getElementById("problemConstraints").textContent = data.constraints || "Standard standard-library constraints apply.";

    const badge = document.getElementById("difficultyBadge");
    badge.className = `badge badge-${data.difficulty}`;
    badge.textContent = data.difficulty.toUpperCase();

    // Render examples
    const examplesContainer = document.getElementById("problemExamples");
    examplesContainer.innerHTML = "";

    (data.examples || []).forEach((ex, idx) => {
        const card = document.createElement("div");
        card.className = "example-card";
        card.innerHTML = `
            <div style="font-weight: 700; color: #cbd5e1; margin-bottom: 0.25rem;">Example ${idx + 1}:</div>
            <div class="example-line"><strong style="color: #94a3b8;">Input:</strong> ${JSON.stringify(ex.input)}</div>
            <div class="example-line"><strong style="color: #94a3b8;">Output:</strong> ${JSON.stringify(ex.output)}</div>
            ${ex.explanation ? `<div class="example-line" style="color: #64748b; font-size: 0.8rem;"><em>Explanation:</em> ${ex.explanation}</div>` : ""}
        `;
        examplesContainer.appendChild(card);
    });
}

function initMonacoEditor(starterCode) {
    require.config({ paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs" } });
    require(["vs/editor/editor.main"], function () {
        const container = document.getElementById("monaco-container");
        container.innerHTML = ""; // Clear existing

        // Define bespoke Atmospheric Acid Glass editor theme
        monaco.editor.defineTheme('prepforge-acid-dark', {
            base: 'vs-dark',
            inherit: true,
            rules: [
                { token: 'comment', foreground: '5e7364', fontStyle: 'italic' },
                { token: 'keyword', foreground: '00ff88', fontStyle: 'bold' },
                { token: 'identifier', foreground: 'ecfdf5' },
                { token: 'string', foreground: '6ee7b7' },
                { token: 'number', foreground: 'f59e0b' },
                { token: 'delimiter', foreground: '94a89a' },
            ],
            colors: {
                'editor.background': '#020503',
                'editor.foreground': '#ecfdf5',
                'editorLineNumber.foreground': '#243a29',
                'editorLineNumber.activeForeground': '#00ff88',
                'editor.lineHighlightBackground': '#051208',
                'editorCursor.foreground': '#00ff88',
                'editor.selectionBackground': '#064e3b',
            }
        });

        editorInstance = monaco.editor.create(container, {
            value: starterCode || "# Write your solution here\n",
            language: "python",
            theme: "prepforge-acid-dark",
            fontSize: 14,
            fontFamily: "'JetBrains Mono', Consolas, monospace",
            minimap: { enabled: false },
            automaticLayout: true,
            scrollBeyondLastLine: false,
            tabSize: 4,
            insertSpaces: true
        });
    });
}

function initTimer(remainingSeconds) {
    if (sessionTimerInstance) {
        sessionTimerInstance.stop();
    }

    sessionTimerInstance = new window.SessionTimer(remainingSeconds, () => {
        // Auto-submit on timer zero
        console.warn("Time expired! Initiating auto-submit...");
        handleSubmit(true);
    });
    sessionTimerInstance.start();
}

async function handleRun() {
    if (!editorInstance || !currentQuestionData) return;
    const btn = document.getElementById("btnRun");
    btn.disabled = true;
    btn.textContent = "Running...";

    switchDrawerTab("results");
    const resultsContainer = document.getElementById("drawerResults");
    resultsContainer.innerHTML = '<div style="color: var(--accent-primary);">Executing visible test cases in Pyodide sandbox...</div>';

    const userCode = editorInstance.getValue();
    const visibleTests = (currentQuestionData.test_cases || []).filter(t => !t.hidden);

    try {
        const runRes = await window.PrepForgeRunner.runTests(
            userCode,
            currentQuestionData.function_name,
            visibleTests,
            "run",
            6000
        );

        renderTestResults(runRes.results, false);
        renderLogs(runRes.logs);
    } catch (err) {
        resultsContainer.innerHTML = `<div style="color: #f87171;">Execution error: ${err.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = "▶ Run Examples";
    }
}

async function handleSubmit(isAutoSubmit = false) {
    if (!editorInstance || !currentQuestionData) return;
    const btn = document.getElementById("btnSubmit");
    const btnTop = document.getElementById("btnSubmitTop");
    btn.disabled = true;
    btnTop.disabled = true;
    btn.textContent = "Submitting...";

    if (sessionTimerInstance) {
        sessionTimerInstance.stop();
    }

    switchDrawerTab("results");
    const resultsContainer = document.getElementById("drawerResults");
    resultsContainer.innerHTML = '<div style="color: var(--accent-primary);">Evaluating code against all hidden test cases in Pyodide...</div>';

    const userCode = editorInstance.getValue();
    const allTests = currentQuestionData.test_cases || [];

    try {
        const runRes = await window.PrepForgeRunner.runTests(
            userCode,
            currentQuestionData.function_name,
            allTests,
            "submit",
            8000
        );

        renderTestResults(runRes.results, true);
        renderLogs(runRes.logs);

        // Post submission to Django backend
        const config = window.SESSION_CONFIG;
        const submitResp = await fetch(`/api/session-questions/${config.sessionQuestionId}/submit/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": config.csrfToken
            },
            body: JSON.stringify({
                code: userCode,
                results: runRes.results,
                auto_submitted: isAutoSubmit
            })
        });

        const submitOutcome = await submitResp.json();

        if (submitOutcome.finished) {
            setTimeout(() => {
                window.location.href = submitOutcome.redirect_url || `/sessions/${config.sessionId}/results/`;
            }, 1200);
        } else {
            // Next question
            setTimeout(() => {
                window.location.reload();
            }, 1200);
        }

    } catch (err) {
        resultsContainer.innerHTML = `<div style="color: #f87171;">Submission failed: ${err.message}</div>`;
        btn.disabled = false;
        btnTop.disabled = false;
        btn.textContent = "✓ Submit";
    }
}

function renderTestResults(results, isSubmitMode) {
    const container = document.getElementById("drawerResults");
    container.innerHTML = "";

    const passedCount = (results || []).filter(r => r.passed).length;
    const totalCount = (results || []).length;
    const allPassed = passedCount === totalCount && totalCount > 0;

    const summaryHeader = document.createElement("div");
    summaryHeader.style.marginBottom = "0.85rem";
    summaryHeader.style.fontSize = "0.92rem";
    summaryHeader.style.fontFamily = "var(--font-mono)";
    summaryHeader.style.fontWeight = "700";
    summaryHeader.innerHTML = allPassed
        ? `<span style="color: var(--emerald-acid); text-shadow: 0 0 10px rgba(0, 255, 136, 0.4);">✓ ALL ${totalCount} TEST BENCHMARKS PASSED (100.0%)</span>`
        : `<span style="color: #ff6b6b; text-shadow: 0 0 10px rgba(239, 68, 68, 0.4);">✗ ${passedCount} / ${totalCount} PASSED (${Math.round(passedCount/totalCount*100)}%)</span>`;

    container.appendChild(summaryHeader);

    (results || []).forEach((r, idx) => {
        const item = document.createElement("div");
        item.style.padding = "0.6rem 0.85rem";
        item.style.marginBottom = "0.5rem";
        item.style.borderRadius = "4px";
        item.style.background = r.passed ? "rgba(0, 255, 136, 0.05)" : "rgba(239, 68, 68, 0.06)";
        item.style.border = `1px solid ${r.passed ? 'rgba(0, 255, 136, 0.28)' : 'rgba(239, 68, 68, 0.3)'}`;
        item.style.fontSize = "0.82rem";
        item.style.fontFamily = "var(--font-mono)";

        const label = r.hidden ? `CASE #${idx + 1} [HIDDEN]` : `CASE #${idx + 1} [VISIBLE]`;
        item.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; font-weight: 700;">
                <span style="color: ${r.passed ? 'var(--emerald-acid)' : '#ff6b6b'}; display: flex; align-items: center; gap: 0.4rem;">
                    <span>${r.passed ? '●' : '▲'}</span> ${r.passed ? 'PASSED' : 'FAILED'} — ${label}
                </span>
                <span style="color: var(--text-muted); font-size: 0.75rem;">${r.ms}ms</span>
            </div>
            ${r.error ? `<div style="color: #fca5a5; margin-top: 0.35rem; padding: 0.4rem 0.6rem; background: rgba(0, 0, 0, 0.4); border-radius: 4px; font-size: 0.78rem;">${r.error}</div>` : ""}
            ${!r.passed && r.actual !== null ? `<div style="color: var(--text-secondary); margin-top: 0.3rem; font-size: 0.78rem;">Actual Output: <code>${JSON.stringify(r.actual)}</code></div>` : ""}
        `;
        container.appendChild(item);
    });
}

function renderLogs(logs) {
    const logsContainer = document.getElementById("drawerLogs");
    logsContainer.textContent = logs || "[No standard output]";
}

function switchDrawerTab(tab) {
    const tabButtons = document.querySelectorAll(".drawer-tab");
    tabButtons.forEach(btn => btn.classList.remove("active"));

    const resultsEl = document.getElementById("drawerResults");
    const logsEl = document.getElementById("drawerLogs");

    if (tab === "results") {
        tabButtons[0].classList.add("active");
        resultsEl.style.display = "block";
        logsEl.style.display = "none";
    } else {
        tabButtons[1].classList.add("active");
        resultsEl.style.display = "none";
        logsEl.style.display = "block";
    }
}

function updateOverlayText(heading, subtext) {
    document.getElementById("overlayHeading").textContent = heading;
    document.getElementById("overlaySubtext").textContent = subtext;
}

function hideVerificationOverlay() {
    const overlay = document.getElementById("verificationOverlay");
    if (overlay) {
        overlay.style.transition = "opacity 0.3s ease";
        overlay.style.opacity = "0";
        setTimeout(() => {
            overlay.style.display = "none";
        }, 300);
    }
}

function showOverlayError(msg) {
    document.getElementById("overlayHeading").textContent = "Generation & Verification Interrupted";
    document.getElementById("overlaySubtext").textContent = msg;
    document.getElementById("overlayError").style.display = "block";
}

function retryFetchQuestion() {
    document.getElementById("overlayError").style.display = "none";
    loadAndVerifyQuestion(1);
}
