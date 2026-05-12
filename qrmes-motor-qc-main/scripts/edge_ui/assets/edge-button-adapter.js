/* global window, document, fetch */
(function initMotorQCEdgeButtonAdapter() {
    "use strict";

    class ManualButtonAdapter {
        constructor(_options) {
            this.source = "manual";
            this.onPress = null;
        }

        async start(onPress) {
            this.onPress = onPress;
        }

        stop() {
            this.onPress = null;
        }
    }

    class KeyboardButtonAdapter {
        constructor(options) {
            this.options = Object.assign(
                {
                    triggerKey: "F8",
                },
                options || {}
            );
            this.source = "keyboard";
            this.onPress = null;
            this.keyHandler = null;
        }

        async start(onPress) {
            this.onPress = onPress;
            const keyName = String(this.options.triggerKey || "F8").toUpperCase();
            this.keyHandler = (evt) => {
                if (String(evt.key || "").toUpperCase() !== keyName) {
                    return;
                }
                if (typeof this.onPress === "function") {
                    this.onPress({
                        source: "keyboard",
                        ts: new Date().toISOString(),
                    });
                }
            };
            document.addEventListener("keydown", this.keyHandler);
        }

        stop() {
            if (this.keyHandler) {
                document.removeEventListener("keydown", this.keyHandler);
            }
            this.keyHandler = null;
            this.onPress = null;
        }
    }

    class LocalBridgeButtonAdapter {
        constructor(options) {
            this.options = Object.assign(
                {
                    baseUrl: "http://127.0.0.1:19091",
                    stationId: "S01",
                    pollMs: 300,
                },
                options || {}
            );
            this.source = "local_bridge";
            this.onPress = null;
            this.timerId = null;
            this.inflight = false;
        }

        async start(onPress) {
            this.onPress = onPress;
            const interval = Math.max(120, Number(this.options.pollMs || 300));
            this.timerId = window.setInterval(() => this.pollOnce(), interval);
            await this.pollOnce();
        }

        async pollOnce() {
            if (this.inflight || typeof this.onPress !== "function") {
                return;
            }
            this.inflight = true;
            try {
                const station = encodeURIComponent(String(this.options.stationId || "S01"));
                const url = `${String(this.options.baseUrl || "").replace(/\/$/, "")}/api/button/next?station_id=${station}`;
                const resp = await fetch(url, {
                    method: "GET",
                    cache: "no-store",
                });
                if (!resp.ok) {
                    return;
                }
                const payload = await resp.json();
                if (!payload || !payload.pressed) {
                    return;
                }
                this.onPress({
                    source: "local_bridge",
                    ts: payload.ts || new Date().toISOString(),
                    eventId: payload.event_id || "",
                });
            } catch (_err) {
                // swallow polling error; bridge may be temporarily unavailable
            } finally {
                this.inflight = false;
            }
        }

        stop() {
            if (this.timerId) {
                window.clearInterval(this.timerId);
                this.timerId = null;
            }
            this.onPress = null;
        }
    }

    function createAdapter(options) {
        const source = String((options && options.source) || "manual").trim().toLowerCase();
        if (source === "keyboard") {
            return new KeyboardButtonAdapter(options);
        }
        if (source === "local_bridge") {
            return new LocalBridgeButtonAdapter(options);
        }
        return new ManualButtonAdapter(options);
    }

    window.MotorQCEdgeButton = {
        ManualButtonAdapter,
        KeyboardButtonAdapter,
        LocalBridgeButtonAdapter,
        createAdapter,
    };
}());
