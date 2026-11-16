/**
 * PrepForge Pyodide Runner Host Controller
 * Manages worker instances, timeout cancellation, and message lifecycle.
 */

class PyodideRunner {
    constructor(workerScriptUrl) {
        this.workerScriptUrl = workerScriptUrl || "/static/interview/js/pyodide.worker.js";
        this.worker = null;
        this.isReady = false;
        this.pendingRequests = new Map();
        this.initWorker();
    }

    initWorker() {
        if (this.worker) {
            try {
                this.worker.terminate();
            } catch (e) {
                console.warn("Error terminating previous worker:", e);
            }
        }

        this.worker = new Worker(this.workerScriptUrl);
        this.isReady = true;

        this.worker.onmessage = (event) => {
            const { id, status, results, logs } = event.data;
            if (this.pendingRequests.has(id)) {
                const req = this.pendingRequests.get(id);
                clearTimeout(req.timer);
                this.pendingRequests.delete(id);
                req.resolve({ status, results, logs });
            }
        };

        this.worker.onerror = (err) => {
            console.error("Pyodide worker level error:", err);
            // Terminate and reject all pending
            for (const [id, req] of this.pendingRequests.entries()) {
                clearTimeout(req.timer);
                req.reject(new Error(`Worker fatal error: ${err.message || 'unknown'}`));
            }
            this.pendingRequests.clear();
            this.initWorker(); // Re-spawn clean worker
        };
    }

    /**
     * Executes code against test cases with safety timeout
     */
    runTests(code, function_name, tests, mode = "run", timeoutMs = 8000) {
        return new Promise((resolve, reject) => {
            const reqId = "job-" + Date.now() + "-" + Math.random().toString(36).substr(2, 6);

            const timer = setTimeout(() => {
                if (this.pendingRequests.has(reqId)) {
                    this.pendingRequests.delete(reqId);
                    // Force terminate worker to stop runaway infinite loops
                    console.warn(`Execution timed out after ${timeoutMs}ms. Terminating worker.`);
                    this.initWorker();

                    resolve({
                        status: "timeout",
                        results: (tests || []).map((t, idx) => ({
                            index: idx,
                            passed: false,
                            actual: null,
                            error: "Time Limit Exceeded (> 2000ms / infinite loop)",
                            ms: timeoutMs,
                            kind: t.kind || "normal",
                            hidden: t.hidden || false
                        })),
                        logs: "[Process Terminated: Execution Timeout]"
                    });
                }
            }, timeoutMs);

            this.pendingRequests.set(reqId, { resolve, reject, timer });

            this.worker.postMessage({
                id: reqId,
                mode: mode,
                code: code,
                function_name: function_name,
                tests: tests
            });
        });
    }
}

// Global singleton instance
window.PrepForgeRunner = new PyodideRunner();
