/* global window, fetch, FormData, URLSearchParams */
(function initMotorQCAPIClient() {
    'use strict';

    class MotorQCAPIClient {
        constructor(baseUrl) {
            this.baseUrl = (baseUrl || '/motor-qc/api').replace(/\/$/, '');
        }

        async request(path, options) {
            const reqOptions = { ...options };
            reqOptions.method = reqOptions.method || 'GET';
            reqOptions.credentials = reqOptions.credentials || 'same-origin';
            reqOptions.headers = { ...(reqOptions.headers || {}) };

            if (reqOptions.body && !(reqOptions.body instanceof FormData)) {
                reqOptions.headers['Content-Type'] = reqOptions.headers['Content-Type'] || 'application/json';
                reqOptions.body = JSON.stringify(reqOptions.body);
            }

            const response = await fetch(`${this.baseUrl}${path}`, reqOptions);
            const contentType = response.headers.get('content-type') || '';
            const payload = contentType.includes('application/json')
                ? await response.json()
                : await response.text();

            if (!response.ok) {
                const message = (payload && (payload.error || payload.message)) || response.statusText || 'Request failed';
                const err = new Error(message);
                err.status = response.status;
                err.payload = payload;
                throw err;
            }

            return payload;
        }

        async requestAbsolute(url, options) {
            const reqOptions = { ...options };
            reqOptions.method = reqOptions.method || 'GET';
            reqOptions.credentials = reqOptions.credentials || 'same-origin';
            reqOptions.headers = { ...(reqOptions.headers || {}) };

            if (reqOptions.body && !(reqOptions.body instanceof FormData)) {
                reqOptions.headers['Content-Type'] = reqOptions.headers['Content-Type'] || 'application/json';
                reqOptions.body = JSON.stringify(reqOptions.body);
            }

            const response = await fetch(url, reqOptions);
            const contentType = response.headers.get('content-type') || '';
            const payload = contentType.includes('application/json')
                ? await response.json()
                : await response.text();

            if (!response.ok) {
                const message = (payload && (payload.error || payload.message)) || response.statusText || 'Request failed';
                const err = new Error(message);
                err.status = response.status;
                err.payload = payload;
                throw err;
            }

            return payload;
        }

        shouldFallbackProxy(err) {
            const status = Number(err && err.status) || 0;
            if (status === 404 || status === 405 || status === 502 || status === 503) {
                return true;
            }
            const payload = err && err.payload;
            const message = String(
                (payload && (payload.message || payload.error)) ||
                (err && err.message) ||
                ''
            ).toLowerCase();
            if (status === 400 && message.includes('proxy path not allowed')) {
                return true;
            }
            return false;
        }

        listProjects() {
            return this.request('/projects');
        }

        listMESProjectsLegacy() {
            return this.requestAbsolute('/edge-api/proxy/api/projects');
        }

        getMESProjectConfig(projectId) {
            return this.requestAbsolute(`/edge-api/proxy/api/projects/${encodeURIComponent(projectId)}/config`);
        }

        getProject(projectId) {
            return this.request(`/projects/${encodeURIComponent(projectId)}`);
        }

        listProjectMotors(projectId, params) {
            const query = new URLSearchParams();
            if (params && params.productType) {
                query.set('productType', params.productType);
            }
            const suffix = query.toString() ? `?${query.toString()}` : '';
            return this.request(`/projects/${encodeURIComponent(projectId)}/motors${suffix}`);
        }

        inspectProjectMotor(projectId, serialNumber, data) {
            return this.request(
                `/projects/${encodeURIComponent(projectId)}/inspect/${encodeURIComponent(serialNumber)}`,
                { method: 'POST', body: data || {} }
            );
        }

        inspectProjectMotorStream(projectId, serialNumber, params, onEvent) {
            if (typeof EventSource === 'undefined') {
                return Promise.reject(new Error('当前浏览器不支持实时进度'));
            }

            const query = new URLSearchParams();
            if (params && params.productType) {
                query.set('productType', params.productType);
            }
            if (params && params.nonce) {
                query.set('nonce', params.nonce);
            }

            const suffix = query.toString() ? `?${query.toString()}` : '';
            const url = `${this.baseUrl}/projects/${encodeURIComponent(projectId)}/inspect-stream/${encodeURIComponent(serialNumber)}${suffix}`;

            return new Promise((resolve, reject) => {
                let settled = false;
                const source = new EventSource(url, { withCredentials: true });

                source.onmessage = (evt) => {
                    let data = null;
                    try {
                        data = JSON.parse(evt.data || '{}');
                    } catch (_err) {
                        data = { event: 'unknown' };
                    }

                    if (typeof onEvent === 'function') {
                        onEvent(data);
                    }

                    if (data.event === 'done') {
                        settled = true;
                        source.close();
                        resolve(data.payload || {});
                    } else if (data.event === 'error') {
                        settled = true;
                        source.close();
                        reject(new Error(data.error || '质检失败'));
                    }
                };

                source.onerror = () => {
                    if (settled) {
                        return;
                    }
                    source.close();
                    reject(new Error('实时进度连接中断'));
                };
            });
        }

        getProjectMotorReport(projectId, serialNumber, params) {
            const query = new URLSearchParams();
            if (params && params.productType) {
                query.set('productType', params.productType);
            }
            const suffix = query.toString() ? `?${query.toString()}` : '';
            return this.request(
                `/projects/${encodeURIComponent(projectId)}/report/${encodeURIComponent(serialNumber)}${suffix}`
            );
        }

        listProjectTasks(projectId, params) {
            const query = new URLSearchParams();
            if (params) {
                if (params.status) {
                    query.set('status', params.status);
                }
                if (params.serial) {
                    query.set('serial', params.serial);
                }
                if (params.process) {
                    query.set('process', params.process);
                }
                if (params.productType) {
                    query.set('productType', params.productType);
                }
                if (params.dateFrom) {
                    query.set('dateFrom', params.dateFrom);
                }
                if (params.dateTo) {
                    query.set('dateTo', params.dateTo);
                }
                if (params.page) {
                    query.set('page', String(params.page));
                }
                if (params.per_page) {
                    query.set('per_page', String(params.per_page));
                }
                if (params.include_children !== undefined) {
                    query.set('include_children', params.include_children ? '1' : '0');
                }
                if (params.seed_if_empty !== undefined) {
                    query.set('seed_if_empty', params.seed_if_empty ? '1' : '0');
                }
            }
            const suffix = query.toString() ? `?${query.toString()}` : '';
            return this.request(`/projects/${encodeURIComponent(projectId)}/tasks${suffix}`);
        }

        getProjectTaskOptions(projectId, params) {
            const query = new URLSearchParams();
            if (params) {
                if (params.status) {
                    query.set('status', params.status);
                }
                if (params.serial) {
                    query.set('serial', params.serial);
                }
                if (params.process) {
                    query.set('process', params.process);
                }
                if (params.productType) {
                    query.set('productType', params.productType);
                }
                if (params.dateFrom) {
                    query.set('dateFrom', params.dateFrom);
                }
                if (params.dateTo) {
                    query.set('dateTo', params.dateTo);
                }
                if (params.q_serial) {
                    query.set('q_serial', params.q_serial);
                }
                if (params.q_process) {
                    query.set('q_process', params.q_process);
                }
                if (params.q_product_type) {
                    query.set('q_product_type', params.q_product_type);
                }
                if (params.limit) {
                    query.set('limit', String(params.limit));
                }
            }
            const suffix = query.toString() ? `?${query.toString()}` : '';
            return this.request(`/projects/${encodeURIComponent(projectId)}/task-options${suffix}`);
        }

        getProjectStorageCheck(projectId, params) {
            const query = new URLSearchParams();
            if (params) {
                if (params.serial) {
                    query.set('serial', params.serial);
                }
                if (params.process) {
                    query.set('process', params.process);
                }
                if (params.status) {
                    query.set('status', params.status);
                }
                if (params.limit) {
                    query.set('limit', String(params.limit));
                }
            }
            const suffix = query.toString() ? `?${query.toString()}` : '';
            return this.request(`/projects/${encodeURIComponent(projectId)}/storage-check${suffix}`);
        }

        getTask(taskId) {
            return this.request(`/tasks/${encodeURIComponent(taskId)}`);
        }

        confirmTask(taskId, data) {
            return this.request(`/tasks/${encodeURIComponent(taskId)}/confirm`, { method: 'POST', body: data || {} });
        }

        confirmFeedback(data) {
            return this.request('/feedback/confirm', { method: 'POST', body: data || {} });
        }

        createProject(data) {
            return this.request('/projects', { method: 'POST', body: data });
        }

        performInspection(data) {
            return this.request('/inspect', { method: 'POST', body: data });
        }

        uploadPhoto(formData) {
            return this.request('/photos/upload', { method: 'POST', body: formData });
        }

        uploadProcessPhoto(formData) {
            return this.uploadPhoto(formData);
        }

        async uploadPhotoViaMobileChannel(formData) {
            try {
                return await this.requestAbsolute('/edge-api/proxy/api/photos/upload', {
                    method: 'POST',
                    body: formData,
                });
            } catch (err) {
                if (!this.shouldFallbackProxy(err)) {
                    throw err;
                }
                return this.requestAbsolute('/api/photos/upload', {
                    method: 'POST',
                    body: formData,
                });
            }
        }

        async analyzeQC(payload) {
            try {
                return await this.requestAbsolute('/edge-api/proxy/api/qc/analyze', {
                    method: 'POST',
                    body: payload || {},
                });
            } catch (err) {
                if (!this.shouldFallbackProxy(err)) {
                    throw err;
                }
                return this.requestAbsolute('/api/qc/analyze', {
                    method: 'POST',
                    body: payload || {},
                });
            }
        }

        recommendSerial(serialNumber, params) {
            const serial = String(serialNumber || '').trim();
            if (!serial) {
                return Promise.resolve({
                    success: false,
                    message: 'serialNumber is required',
                });
            }
            const query = new URLSearchParams();
            if (params) {
                if (params.current_project) {
                    query.set('current_project', params.current_project);
                }
                if (params.current_product_type) {
                    query.set('current_product_type', params.current_product_type);
                }
            }
            const suffix = query.toString() ? `?${query.toString()}` : '';
            return this.requestAbsolute(`/api/h2/recommend/${encodeURIComponent(serial)}${suffix}`);
        }

        pollTaskByProcess(projectId, serialNumber, processName, params) {
            const queryParams = {
                serial: serialNumber,
                process: processName,
                include_children: true,
                per_page: 20,
                page: 1,
                seed_if_empty: false,
                ...(params || {}),
            };
            return this.listProjectTasks(projectId, queryParams);
        }

        getDefectReport(projectCode, params) {
            const query = new URLSearchParams();
            if (params) {
                if (params.start_date) {
                    query.set('start_date', params.start_date);
                }
                if (params.end_date) {
                    query.set('end_date', params.end_date);
                }
            }
            const suffix = query.toString() ? `?${query.toString()}` : '';
            return this.request(`/reports/defects/${encodeURIComponent(projectCode)}${suffix}`);
        }

        getProcessStepReport(projectCode) {
            return this.request(`/reports/process-steps/${encodeURIComponent(projectCode)}`);
        }
    }

    window.MotorQCAPIClient = MotorQCAPIClient;
    window.motorQCAPI = new MotorQCAPIClient();
}());
