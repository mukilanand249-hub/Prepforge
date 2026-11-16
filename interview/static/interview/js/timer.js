/**
 * PrepForge Countdown Timer
 * Handles synchronized timer tracking, visual urgency cues, and auto-submit triggers.
 */

class SessionTimer {
    constructor(remainingSeconds, onExpireCallback) {
        this.remainingSeconds = remainingSeconds;
        this.onExpireCallback = onExpireCallback;
        this.interval = null;
        this.displayEl = document.getElementById("timerDisplay");
        this.textEl = document.getElementById("timerTime");
        this.isExpired = false;
    }

    start() {
        this.updateDisplay();
        if (this.remainingSeconds <= 0) {
            this.triggerExpire();
            return;
        }

        this.interval = setInterval(() => {
            this.remainingSeconds -= 1;
            this.updateDisplay();

            if (this.remainingSeconds <= 60 && this.displayEl) {
                this.displayEl.classList.add("timer-urgent");
            }

            if (this.remainingSeconds <= 0) {
                this.triggerExpire();
            }
        }, 1000);
    }

    updateDisplay() {
        if (!this.textEl) return;
        const mins = Math.floor(Math.max(0, this.remainingSeconds) / 60);
        const secs = Math.max(0, this.remainingSeconds) % 60;
        this.textEl.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }

    triggerExpire() {
        if (this.isExpired) return;
        this.isExpired = true;
        this.stop();
        if (this.textEl) this.textEl.textContent = "00:00";
        if (typeof this.onExpireCallback === "function") {
            this.onExpireCallback();
        }
    }

    stop() {
        if (this.interval) {
            clearInterval(this.interval);
            this.interval = null;
        }
    }
}

window.SessionTimer = SessionTimer;
