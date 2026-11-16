/**
 * PrepForge Pyodide Web Worker
 * In-browser Python sandbox for verification and user code execution.
 */

// Import Pyodide script from CDN
importScripts("https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js");

let pyodide = null;
let isInitializing = false;
let initPromise = null;

async function getPyodide() {
    if (pyodide) return pyodide;
    if (isInitializing) return initPromise;

    isInitializing = true;
    initPromise = loadPyodide({
        indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
    }).then(async (instance) => {
        pyodide = instance;
        isInitializing = false;
        // Preload standard modules
        await pyodide.runPythonAsync(`
import sys
import io
import json
import math
import copy
import traceback

def compare_results(actual, expected):
    if actual == expected:
        return True
    # Float tolerance comparison
    if isinstance(actual, (float, int)) and isinstance(expected, (float, int)):
        try:
            return math.isclose(float(actual), float(expected), rel_tol=1e-5, abs_tol=1e-5)
        except Exception:
            pass
    # List/tuple equivalence
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        if len(actual) != len(expected):
            return False
        return all(compare_results(a, e) for a, e in zip(actual, expected))
    # Dict key/value comparison
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual.keys()) != set(expected.keys()):
            return False
        return all(compare_results(actual[k], expected[k]) for k in actual)
    return False
        `);
        return pyodide;
    });

    return initPromise;
}

self.onmessage = async (event) => {
    const { id, mode, code, function_name, tests } = event.data;

    try {
        const py = await getPyodide();

        // Pass payload into Python environment via globals
        py.globals.set("__run_code__", code);
        py.globals.set("__fn_name__", function_name);
        py.globals.set("__raw_tests__", JSON.stringify(tests || []));

        const executionScript = `
import sys
import io
import json
import copy
import traceback
import time

stdout_trap = io.StringIO()
old_stdout = sys.stdout
sys.stdout = stdout_trap

run_status = "ok"
test_results = []
tests_list = json.loads(__raw_tests__)

# Isolate execution namespace
ns = {}
try:
    exec(__run_code__, ns)
except Exception as e:
    run_status = "error"
    err_msg = traceback.format_exc().strip().splitlines()[-1]
    for idx, t in enumerate(tests_list):
        test_results.append({
            "index": idx,
            "passed": False,
            "actual": None,
            "error": f"Compilation/Syntax Error: {err_msg}",
            "ms": 0,
            "kind": t.get("kind", "normal"),
            "hidden": t.get("hidden", False)
        })
else:
    if __fn_name__ not in ns or not callable(ns[__fn_name__]):
        run_status = "error"
        for idx, t in enumerate(tests_list):
            test_results.append({
                "index": idx,
                "passed": False,
                "actual": None,
                "error": f"Function '{__fn_name__}' not defined in code.",
                "ms": 0,
                "kind": t.get("kind", "normal"),
                "hidden": t.get("hidden", False)
            })
    else:
        target_fn = ns[__fn_name__]
        for idx, test in enumerate(tests_list):
            args = test.get("input", [])
            expected = test.get("expected", None)
            kind = test.get("kind", "normal")
            hidden = test.get("hidden", False)

            # Deep copy arguments to prevent in-place mutation side effects
            args_copy = copy.deepcopy(args)

            t0 = time.perf_counter()
            try:
                actual = target_fn(*args_copy)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                passed = compare_results(actual, expected)
                test_results.append({
                    "index": idx,
                    "passed": bool(passed),
                    "actual": actual,
                    "error": None,
                    "ms": elapsed_ms,
                    "kind": kind,
                    "hidden": hidden
                })
            except Exception as e:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                err_msg = traceback.format_exc().strip().splitlines()[-1]
                test_results.append({
                    "index": idx,
                    "passed": False,
                    "actual": None,
                    "error": err_msg,
                    "ms": elapsed_ms,
                    "kind": kind,
                    "hidden": hidden
                })

sys.stdout = old_stdout
captured_logs = stdout_trap.getvalue()[:10000] # Cap output at 10KB
json.dumps({
    "status": run_status,
    "results": test_results,
    "logs": captured_logs
})
        `;

        const rawResult = await py.runPythonAsync(executionScript);
        const parsed = JSON.parse(rawResult);

        self.postMessage({
            id: id,
            status: parsed.status,
            results: parsed.results,
            logs: parsed.logs
        });

    } catch (err) {
        self.postMessage({
            id: id,
            status: "error",
            results: (tests || []).map((t, idx) => ({
                index: idx,
                passed: false,
                actual: null,
                error: err.message || "Runtime exception",
                ms: 0,
                kind: t.kind || "normal",
                hidden: t.hidden || false
            })),
            logs: ""
        });
    }
};
