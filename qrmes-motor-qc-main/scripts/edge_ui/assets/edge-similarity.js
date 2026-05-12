/* global window, document */
(function initMotorQCEdgeSimilarity() {
    "use strict";

    const DEFAULT_THRESHOLDS = {
        screw: { ssim: 0.985, phash: 6 },
        glue: { ssim: 0.98, phash: 8 },
    };

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function normalizeRoi(roi, width, height) {
        if (!roi || typeof roi !== "object") {
            return { x: 0, y: 0, w: width, h: height };
        }
        const x = clamp(Math.floor(Number(roi.x) || 0), 0, Math.max(0, width - 1));
        const y = clamp(Math.floor(Number(roi.y) || 0), 0, Math.max(0, height - 1));
        const maxW = Math.max(1, width - x);
        const maxH = Math.max(1, height - y);
        const w = clamp(Math.floor(Number(roi.w) || width), 1, maxW);
        const h = clamp(Math.floor(Number(roi.h) || height), 1, maxH);
        return { x, y, w, h };
    }

    function createTinyGray(canvas, roi, size) {
        if (!canvas) {
            return [];
        }
        const roiNorm = normalizeRoi(roi, canvas.width, canvas.height);
        const tiny = document.createElement("canvas");
        tiny.width = size;
        tiny.height = size;
        const tctx = tiny.getContext("2d", { willReadFrequently: true });
        tctx.drawImage(
            canvas,
            roiNorm.x,
            roiNorm.y,
            roiNorm.w,
            roiNorm.h,
            0,
            0,
            size,
            size
        );
        const imageData = tctx.getImageData(0, 0, size, size).data;
        const gray = new Array(size * size);
        for (let i = 0, p = 0; i < gray.length; i += 1, p += 4) {
            gray[i] = Math.round(0.299 * imageData[p] + 0.587 * imageData[p + 1] + 0.114 * imageData[p + 2]);
        }
        return gray;
    }

    function pseudoSSIM(a, b) {
        if (!a.length || a.length !== b.length) {
            return 0;
        }
        let mse = 0;
        for (let i = 0; i < a.length; i += 1) {
            const d = a[i] - b[i];
            mse += d * d;
        }
        mse /= a.length;
        const score = 1 - mse / (255 * 255);
        return clamp(score, 0, 1);
    }

    function phashBits(gray32) {
        if (!gray32 || gray32.length < 1024) {
            return new Array(64).fill(0);
        }
        const bits = new Array(64);
        let sum = 0;
        for (let y = 0; y < 8; y += 1) {
            for (let x = 0; x < 8; x += 1) {
                const sx = x * 4 + 2;
                const sy = y * 4 + 2;
                const value = gray32[sy * 32 + sx] || 0;
                sum += value;
                bits[y * 8 + x] = value;
            }
        }
        const avg = sum / 64;
        for (let i = 0; i < 64; i += 1) {
            bits[i] = bits[i] >= avg ? 1 : 0;
        }
        return bits;
    }

    function hammingDistance(bitsA, bitsB) {
        if (!bitsA || !bitsB || bitsA.length !== bitsB.length) {
            return 64;
        }
        let diff = 0;
        for (let i = 0; i < bitsA.length; i += 1) {
            if (bitsA[i] !== bitsB[i]) {
                diff += 1;
            }
        }
        return diff;
    }

    function compareSingleRoi(prevCanvas, currCanvas, roi) {
        const prevGray = createTinyGray(prevCanvas, roi, 32);
        const currGray = createTinyGray(currCanvas, roi, 32);
        const ssim = pseudoSSIM(prevGray, currGray);
        const phash = hammingDistance(phashBits(prevGray), phashBits(currGray));
        return { ssim, phash };
    }

    function aggregateRoiMetrics(prevCanvas, currCanvas, rois) {
        const safeRois = Array.isArray(rois) && rois.length ? rois : [{ x: 0, y: 0, w: currCanvas.width, h: currCanvas.height }];
        let minSsim = 1;
        let maxPhash = 0;
        for (const roi of safeRois) {
            const item = compareSingleRoi(prevCanvas, currCanvas, roi);
            minSsim = Math.min(minSsim, item.ssim);
            maxPhash = Math.max(maxPhash, item.phash);
        }
        return {
            ssim: Number(minSsim.toFixed(4)),
            phash: Number(maxPhash.toFixed(0)),
        };
    }

    function compareFrames(prevCanvas, currCanvas, roiConfig, thresholds) {
        if (!currCanvas) {
            return {
                changed: false,
                reason: "no_current_frame",
                metrics: null,
            };
        }
        if (!prevCanvas) {
            return {
                changed: true,
                reason: "first_frame",
                metrics: {
                    screw_ssim: null,
                    screw_phash: null,
                    glue_ssim: null,
                    glue_phash: null,
                },
            };
        }

        const config = Object.assign({}, DEFAULT_THRESHOLDS, thresholds || {});
        const screwMetrics = aggregateRoiMetrics(prevCanvas, currCanvas, (roiConfig || {}).screw || []);
        const glueMetrics = aggregateRoiMetrics(prevCanvas, currCanvas, (roiConfig || {}).glue || []);

        const screwSame = screwMetrics.ssim >= config.screw.ssim && screwMetrics.phash < config.screw.phash;
        const glueSame = glueMetrics.ssim >= config.glue.ssim && glueMetrics.phash < config.glue.phash;
        const changed = !(screwSame && glueSame);

        return {
            changed,
            reason: changed ? "delta_detected" : "same_as_last_uploaded",
            metrics: {
                screw_ssim: screwMetrics.ssim,
                screw_phash: screwMetrics.phash,
                glue_ssim: glueMetrics.ssim,
                glue_phash: glueMetrics.phash,
            },
        };
    }

    function frameHash(canvas) {
        const gray = createTinyGray(canvas, null, 16);
        let hash = 2166136261;
        for (let i = 0; i < gray.length; i += 1) {
            hash ^= gray[i];
            hash = (hash * 16777619) >>> 0;
        }
        return `fnv32:${hash.toString(16).padStart(8, "0")}`;
    }

    window.MotorQCEdgeSimilarity = {
        compareFrames,
        frameHash,
        DEFAULT_THRESHOLDS,
    };
}());
