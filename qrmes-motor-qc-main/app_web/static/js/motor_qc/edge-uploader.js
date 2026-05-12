/* global window, FormData, FileReader, setTimeout */
(function initMotorQCEdgeUploader() {
    "use strict";

    function sleep(ms) {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    class EdgeCaptureUploader {
        constructor(apiClient, options) {
            this.api = apiClient;
            this.options = Object.assign(
                {
                    maxRetries: 4,
                    baseDelayMs: 1000,
                    onQueueChange: null,
                },
                options || {}
            );
            this.queue = [];
            this.running = false;
        }

        getQueueSize() {
            return this.queue.length;
        }

        enqueueUpload(sessionContext, capturePayload) {
            return new Promise((resolve, reject) => {
                const job = {
                    sessionContext,
                    capturePayload,
                    retries: 0,
                    resolve,
                    reject,
                };
                this.queue.push(job);
                this.notifyQueueChange();
                this.pump();
            });
        }

        async pump() {
            if (this.running) {
                return;
            }
            this.running = true;
            try {
                while (this.queue.length > 0) {
                    const job = this.queue[0];
                    try {
                        const result = await this.performUpload(job.sessionContext, job.capturePayload);
                        this.queue.shift();
                        this.notifyQueueChange();
                        job.resolve(result);
                    } catch (err) {
                        job.retries += 1;
                        if (job.retries > this.options.maxRetries) {
                            this.queue.shift();
                            this.notifyQueueChange();
                            job.reject(err);
                            continue;
                        }
                        const delay = this.options.baseDelayMs * Math.pow(2, job.retries - 1);
                        await sleep(delay);
                    }
                }
            } finally {
                this.running = false;
                this.notifyQueueChange();
            }
        }

        notifyQueueChange() {
            if (typeof this.options.onQueueChange === "function") {
                this.options.onQueueChange(this.getQueueSize());
            }
        }

        blobToBase64(blob) {
            return new Promise((resolve, reject) => {
                if (!blob) {
                    reject(new Error("empty blob"));
                    return;
                }
                const reader = new FileReader();
                reader.onload = () => {
                    const raw = String(reader.result || "");
                    const idx = raw.indexOf("base64,");
                    if (idx < 0) {
                        reject(new Error("invalid data url"));
                        return;
                    }
                    resolve(raw.slice(idx + 7));
                };
                reader.onerror = () => reject(new Error("read blob failed"));
                reader.readAsDataURL(blob);
            });
        }

        async uploadToMobileStorage(sessionContext, capturePayload) {
            const formData = new FormData();
            const safeProject = String(sessionContext.projectId || "").trim();
            const safeProjectName = String(sessionContext.projectName || safeProject || "").trim();
            const safeProcess = String(sessionContext.processName || "").trim();
            const safeSerial = String(sessionContext.serialNumber || "").trim();
            const safeProductType = String(sessionContext.productType || "").trim();
            const imageName = String(capturePayload.fileName || "capture.jpg").trim() || "capture.jpg";

            formData.append("photo", capturePayload.blob, imageName);
            formData.append("productSerial", safeSerial);
            formData.append("processStep", safeProcess);
            formData.append("projectName", safeProjectName || safeProject);
            formData.append("projectCode", safeProject);
            formData.append("productType", safeProductType);
            formData.append("capturedAt", String(capturePayload.capturedAt || "").trim());
            formData.append("frameHash", String(capturePayload.frameHash || "").trim());
            formData.append("isFinal", capturePayload.isFinal ? "1" : "0");
            formData.append("stationId", String(sessionContext.stationId || "").trim());

            return this.api.uploadPhotoViaMobileChannel(formData);
        }

        async performUpload(sessionContext, capturePayload) {
            const safeProcess = String(sessionContext.processName || "").trim();
            const safeProject = String(sessionContext.projectId || "").trim();
            if (!safeProject || !safeProcess) {
                throw new Error("missing project/process context");
            }

            const uploadMode = String(sessionContext.uploadMode || "task_center").trim().toLowerCase();
            if (uploadMode === "mobile_qc") {
                const mobileUploadResult = await this.uploadToMobileStorage(sessionContext, capturePayload);
                const base64Image = await this.blobToBase64(capturePayload.blob);
                const payload = {
                    project_name: safeProjectName || safeProject,
                    process_name: safeProcess,
                    product_serial: String(sessionContext.serialNumber || "").trim(),
                    product_type: String(sessionContext.productType || "").trim(),
                    photo_base64: [base64Image],
                    process_context: (sessionContext.processContext && typeof sessionContext.processContext === "object")
                        ? sessionContext.processContext
                        : {},
                    pre_prompt: String(
                        (sessionContext.processContext && sessionContext.processContext.pre_prompt) || ""
                    ).trim(),
                };
                const qcResult = await this.api.analyzeQC(payload);
                if (!qcResult || qcResult.success === false) {
                    const errMsg = (qcResult && (qcResult.summary || qcResult.error)) || "mobile qc analyze failed";
                    throw new Error(String(errMsg));
                }
                return {
                    mode: "mobile_qc",
                    task_status: String(qcResult.status || "unknown"),
                    summary: String(qcResult.summary || ""),
                    confidence: Number(qcResult.confidence || 0) || 0,
                    findings_count: Array.isArray(qcResult.findings) ? qcResult.findings.length : 0,
                    raw: qcResult,
                    upload: mobileUploadResult || {},
                };
            }

            const formData = new FormData();

            formData.append("project_code", safeProject);
            formData.append("process_step", safeProcess);
            formData.append("serial_number", String(sessionContext.serialNumber || "").trim());
            formData.append("product_type", String(sessionContext.productType || "").trim());

            formData.append("is_final", capturePayload.isFinal ? "1" : "0");
            formData.append("station_id", String(sessionContext.stationId || "").trim());
            formData.append("frame_hash", String(capturePayload.frameHash || "").trim());
            formData.append("captured_at", String(capturePayload.capturedAt || "").trim());
            formData.append(
                "similarity_json",
                JSON.stringify(capturePayload.similarity || {})
            );

            const imageName = String(capturePayload.fileName || "capture.jpg").trim() || "capture.jpg";
            formData.append("file", capturePayload.blob, imageName);

            return this.api.uploadProcessPhoto(formData);
        }
    }

    window.MotorQCEdgeUploader = {
        EdgeCaptureUploader,
    };
}());
