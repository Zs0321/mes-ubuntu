/* global window, navigator, document, fetch, URL, Image */
(function initMotorQCEdgeCameraAdapter() {
    "use strict";

    function cloneCanvas(source) {
        if (!source || !source.width || !source.height) {
            return null;
        }
        const canvas = document.createElement("canvas");
        canvas.width = source.width;
        canvas.height = source.height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(source, 0, 0);
        return canvas;
    }

    class BrowserCameraAdapter {
        constructor(options) {
            this.options = Object.assign(
                {
                    width: 1280,
                    height: 720,
                    facingMode: "environment",
                },
                options || {}
            );
            this.videoEl = null;
            this.stream = null;
        }

        getPreviewMode() {
            return "video";
        }

        async start(videoEl) {
            if (!videoEl) {
                throw new Error("missing video element");
            }
            this.videoEl = videoEl;
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error("browser camera is not supported");
            }

            const constraints = {
                video: {
                    width: { ideal: this.options.width },
                    height: { ideal: this.options.height },
                    facingMode: this.options.facingMode,
                },
                audio: false,
            };
            this.stream = await navigator.mediaDevices.getUserMedia(constraints);
            this.videoEl.srcObject = this.stream;
            await this.videoEl.play();
        }

        stop() {
            if (this.videoEl) {
                this.videoEl.pause();
                this.videoEl.srcObject = null;
            }
            if (this.stream) {
                for (const track of this.stream.getTracks()) {
                    track.stop();
                }
            }
            this.stream = null;
        }

        isReady() {
            return Boolean(this.videoEl && this.videoEl.videoWidth > 0 && this.videoEl.videoHeight > 0);
        }

        captureFrame() {
            if (!this.isReady()) {
                return null;
            }
            const canvas = document.createElement("canvas");
            canvas.width = this.videoEl.videoWidth || this.options.width;
            canvas.height = this.videoEl.videoHeight || this.options.height;
            const ctx = canvas.getContext("2d");
            ctx.drawImage(this.videoEl, 0, 0, canvas.width, canvas.height);
            return canvas;
        }
    }

    class MockCameraAdapter {
        constructor(options) {
            this.options = Object.assign(
                {
                    width: 1280,
                    height: 720,
                    fps: 10,
                },
                options || {}
            );
            this.previewCanvas = null;
            this.ready = false;
            this.timerId = null;
        }

        getPreviewMode() {
            return "canvas";
        }

        async start(_videoEl, canvasEl) {
            this.previewCanvas = canvasEl;
            if (!this.previewCanvas) {
                throw new Error("missing preview canvas");
            }
            this.previewCanvas.width = this.options.width;
            this.previewCanvas.height = this.options.height;
            this.ready = true;

            const interval = Math.max(60, Math.floor(1000 / Math.max(1, this.options.fps)));
            this.timerId = window.setInterval(() => this.drawMockFrame(), interval);
            this.drawMockFrame();
        }

        drawMockFrame() {
            if (!this.previewCanvas) {
                return;
            }
            const ctx = this.previewCanvas.getContext("2d");
            const now = Date.now();
            const x = 60 + (Math.floor(now / 500) % 15) * 24;
            const y = 80 + (Math.floor(now / 700) % 8) * 20;

            ctx.fillStyle = "#101827";
            ctx.fillRect(0, 0, this.previewCanvas.width, this.previewCanvas.height);
            ctx.fillStyle = "#1f2937";
            ctx.fillRect(60, 60, this.previewCanvas.width - 120, this.previewCanvas.height - 120);
            ctx.fillStyle = "#0ea5e9";
            ctx.fillRect(x, y, 80, 80);
            ctx.fillStyle = "#22c55e";
            ctx.fillRect(this.previewCanvas.width - x - 120, this.previewCanvas.height - y - 120, 100, 30);

            ctx.fillStyle = "#e5e7eb";
            ctx.font = "24px monospace";
            ctx.fillText(new Date(now).toLocaleTimeString("zh-CN"), 80, this.previewCanvas.height - 80);
            ctx.fillText("MOCK CAMERA", 80, 96);
        }

        stop() {
            if (this.timerId) {
                window.clearInterval(this.timerId);
                this.timerId = null;
            }
            this.ready = false;
        }

        isReady() {
            return this.ready && !!this.previewCanvas;
        }

        captureFrame() {
            if (!this.isReady()) {
                return null;
            }
            return cloneCanvas(this.previewCanvas);
        }
    }

    class LocalBridgeCameraAdapter {
        constructor(options) {
            this.options = Object.assign(
                {
                    width: 1280,
                    height: 720,
                    fps: 5,
                    baseUrl: "http://127.0.0.1:19091",
                    stationId: "S01",
                    requestTimeoutMs: 2500,
                    decodeTimeoutMs: 2000,
                    onFrameMeta: null,
                },
                options || {}
            );
            this.previewCanvas = null;
            this.ready = false;
            this.timerId = null;
            this.fetching = false;
            this.errorCount = 0;
            this.frameMeta = {
                mock: false,
                source: "",
                error: "",
            };
            this.lastFrameMetaSignature = "";
        }

        getPreviewMode() {
            return "canvas";
        }

        async start(_videoEl, canvasEl) {
            this.previewCanvas = canvasEl;
            if (!this.previewCanvas) {
                throw new Error("missing preview canvas");
            }
            this.previewCanvas.width = this.options.width;
            this.previewCanvas.height = this.options.height;
            const interval = Math.max(80, Math.floor(1000 / Math.max(1, this.options.fps)));
            this.timerId = window.setInterval(() => {
                this.pullFrame();
            }, interval);
            await this.pullFrame();
            if (!this.ready) {
                throw new Error("local bridge camera not ready");
            }
        }

        async pullFrame() {
            if (!this.previewCanvas || this.fetching) {
                return;
            }
            this.fetching = true;
            try {
                const station = encodeURIComponent(String(this.options.stationId || "S01").replace(/\^+$/, ""));
                const base = String(this.options.baseUrl || "").replace(/\/$/, "");
                const url = `${base}/api/camera/frame?station_id=${station}&_ts=${Date.now()}`;
                const meta = await this.drawUrl(url);
                this.ready = true;
                this.errorCount = 0;
                this.emitFrameMeta(meta);
            } catch (_err) {
                this.errorCount += 1;
                if (this.errorCount >= 8 && !this.ready) {
                    this.ready = false;
                }
                const msg = String((_err && _err.message) || _err || "bridge frame unavailable");
                this.emitFrameMeta({
                    mock: true,
                    source: String(this.frameMeta.source || ""),
                    error: msg,
                });
            } finally {
                this.fetching = false;
            }
        }

        emitFrameMeta(meta) {
            const normalized = Object.assign(
                {
                    mock: false,
                    source: "",
                    error: "",
                },
                meta || {}
            );
            this.frameMeta = normalized;
            const signature = `${normalized.mock ? "1" : "0"}|${normalized.source || ""}|${normalized.error || ""}`;
            if (signature === this.lastFrameMetaSignature) {
                return;
            }
            this.lastFrameMetaSignature = signature;
            if (typeof this.options.onFrameMeta === "function") {
                try {
                    this.options.onFrameMeta(Object.assign({}, normalized));
                } catch (_err) {
                    // callback errors should not interrupt camera polling
                }
            }
        }

        async drawUrl(url) {
            if (!url || !this.previewCanvas) {
                throw new Error("invalid url/canvas");
            }
            const timeoutMs = Math.max(800, Number(this.options.requestTimeoutMs || 0) || 2500);
            const aborter = new AbortController();
            const timeoutId = window.setTimeout(() => {
                aborter.abort();
            }, timeoutMs);
            let response;
            try {
                response = await fetch(url, {
                    method: "GET",
                    cache: "no-store",
                    signal: aborter.signal,
                });
            } catch (err) {
                if (err && err.name === "AbortError") {
                    throw new Error(`bridge frame timeout>${timeoutMs}ms`);
                }
                throw err;
            } finally {
                window.clearTimeout(timeoutId);
            }
            if (!response || !response.ok) {
                const status = response ? Number(response.status || 0) : 0;
                throw new Error(`bridge frame http ${status || "unknown"}`);
            }
            const blob = await response.blob();
            await this.drawBlob(blob);
            return {
                mock: String(response.headers.get("X-Edge-Camera-Mock") || "0") === "1",
                source: String(response.headers.get("X-Edge-Camera-Source") || "").trim().toLowerCase(),
                error: String(response.headers.get("X-Edge-Camera-Error") || "").trim(),
            };
        }

        drawBlob(blob) {
            return new Promise((resolve, reject) => {
                if (!blob || !this.previewCanvas) {
                    reject(new Error("invalid frame blob"));
                    return;
                }
                const objectUrl = URL.createObjectURL(blob);
                const decodeTimeoutMs = Math.max(600, Number(this.options.decodeTimeoutMs || 0) || 2000);
                const img = new Image();
                const timerId = window.setTimeout(() => {
                    img.onload = null;
                    img.onerror = null;
                    URL.revokeObjectURL(objectUrl);
                    reject(new Error(`bridge frame decode timeout>${decodeTimeoutMs}ms`));
                }, decodeTimeoutMs);
                img.onload = () => {
                    window.clearTimeout(timerId);
                    const width = img.naturalWidth || this.options.width;
                    const height = img.naturalHeight || this.options.height;
                    this.previewCanvas.width = width;
                    this.previewCanvas.height = height;
                    const ctx = this.previewCanvas.getContext("2d");
                    ctx.drawImage(img, 0, 0, width, height);
                    URL.revokeObjectURL(objectUrl);
                    resolve();
                };
                img.onerror = () => {
                    window.clearTimeout(timerId);
                    URL.revokeObjectURL(objectUrl);
                    reject(new Error("decode bridge frame failed"));
                };
                img.src = objectUrl;
            });
        }

        stop() {
            if (this.timerId) {
                window.clearInterval(this.timerId);
                this.timerId = null;
            }
            this.ready = false;
            this.fetching = false;
        }

        isReady() {
            return this.ready && !!this.previewCanvas && this.previewCanvas.width > 0;
        }

        getLastFrameMeta() {
            return Object.assign({}, this.frameMeta || {});
        }

        captureFrame() {
            if (!this.isReady()) {
                return null;
            }
            return cloneCanvas(this.previewCanvas);
        }
    }

    function createAdapter(options) {
        const source = String((options && options.source) || "").trim().toLowerCase();
        if (source === "mock") {
            return new MockCameraAdapter(options);
        }
        if (source === "local_bridge") {
            return new LocalBridgeCameraAdapter(options);
        }
        return new BrowserCameraAdapter(options);
    }

    window.MotorQCEdgeCamera = {
        BrowserCameraAdapter,
        MockCameraAdapter,
        LocalBridgeCameraAdapter,
        createAdapter,
    };
}());
