/* global window */
(function initMotorQCEdgeStationStore() {
    "use strict";

    const ALLOWED_STATES = new Set(["IDLE", "RUNNING", "ENDING", "CLOSED", "ERROR"]);

    class EdgeSessionStore {
        constructor(initialState) {
            this.listeners = new Set();
            this.state = Object.assign(this.getInitialState(), initialState || {});
        }

        getInitialState() {
            return {
                sessionState: "IDLE",
                stationId: "S01",
                operatorId: "",
                serialNumber: "",
                projectId: "",
                projectName: "",
                productType: "",
                processName: "",
                processOrder: 0,
                seq: 0,
                tickSeconds: 15,
                countdownSeconds: 15,
                roiConfig: {
                    screw: [],
                    glue: [],
                },
                lastSimilarity: null,
                lastUpload: null,
                queueSize: 0,
                backendStatus: "unknown",
                cameraStatus: "stopped",
                buttonStatus: "manual",
                timeline: [],
            };
        }

        getState() {
            return this.state;
        }

        setState(patch) {
            if (!patch || typeof patch !== "object") {
                return;
            }
            this.state = Object.assign({}, this.state, patch);
            this.emit();
        }

        transition(nextState) {
            const normalized = String(nextState || "").trim().toUpperCase();
            if (!ALLOWED_STATES.has(normalized)) {
                return;
            }
            this.setState({ sessionState: normalized });
        }

        subscribe(listener) {
            if (typeof listener !== "function") {
                return () => {};
            }
            this.listeners.add(listener);
            return () => this.listeners.delete(listener);
        }

        addTimelineEvent(event) {
            const nextEvent = Object.assign(
                {
                    ts: new Date().toISOString(),
                    type: "INFO",
                },
                event || {}
            );
            const timeline = [nextEvent].concat(this.state.timeline || []).slice(0, 120);
            this.setState({ timeline });
        }

        resetForNextSession() {
            const baseline = this.getInitialState();
            baseline.stationId = this.state.stationId || "S01";
            baseline.operatorId = this.state.operatorId || "";
            baseline.backendStatus = this.state.backendStatus || "unknown";
            baseline.cameraStatus = this.state.cameraStatus || "stopped";
            baseline.tickSeconds = this.state.tickSeconds || 15;
            baseline.countdownSeconds = baseline.tickSeconds;
            this.state = baseline;
            this.emit();
        }

        emit() {
            for (const listener of this.listeners) {
                try {
                    listener(this.state);
                } catch (_err) {
                    // ignore listener errors to keep store stable
                }
            }
        }
    }

    window.MotorQCEdgeSessionStore = EdgeSessionStore;
}());
