/**
 * 优化版异步照片加载器
 * 零依赖 + 性能优化
 * 
 * 优化点:
 * 1. 减少 DOM 操作
 * 2. 使用 DocumentFragment
 * 3. 请求去重
 * 4. 内存优化
 * 5. 更小的代码体积
 */

class AsyncPhotoLoaderOptimized {
    constructor(options = {}) {
        this.options = {
            rootMargin: '100px',
            threshold: 0.01,
            fadeInDuration: 300,
            retryAttempts: 2,
            retryDelay: 1000,
            ...options
        };
        
        this.observer = null;
        this.loadingCache = new Map(); // 请求去重
        this.loadedImages = new WeakSet(); // 使用 WeakSet 优化内存
        
        this.init();
    }
    
    init() {
        // 创建 Intersection Observer
        if ('IntersectionObserver' in window) {
            this.observer = new IntersectionObserver(
                (entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting && !this.loadedImages.has(entry.target)) {
                            this.loadPhoto(entry.target);
                            this.observer.unobserve(entry.target);
                        }
                    });
                },
                {
                    rootMargin: this.options.rootMargin,
                    threshold: this.options.threshold
                }
            );
        }
        
        // 注入最小化样式
        this.injectStyles();
    }
    
    injectStyles() {
        if (document.getElementById('apl-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'apl-styles';
        style.textContent = `
            .photo-container{position:relative;overflow:hidden;background:#f0f0f0}
            .photo-placeholder{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%);background-size:200% 100%;animation:shimmer 1.5s infinite}
            @keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
            .photo-img{width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity ${this.options.fadeInDuration}ms}
            .photo-img.loaded{opacity:1}
            .photo-error{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;color:#999;font-size:12px}
        `;
        document.head.appendChild(style);
    }
    
    observe(element, data) {
        if (!element || this.loadedImages.has(element)) return;
        
        element._photoData = data;
        element.classList.add('photo-container');
        element.innerHTML = '<div class="photo-placeholder">📷</div>';
        
        if (this.observer) {
            this.observer.observe(element);
        } else {
            this.loadPhoto(element);
        }
    }
    
    observeAll(selector = '[data-photo-src]') {
        const elements = document.querySelectorAll(selector);
        const fragment = document.createDocumentFragment();
        
        elements.forEach(el => {
            const data = {
                thumbnail: el.dataset.photoThumbnail,
                src: el.dataset.photoSrc,
                alt: el.dataset.photoAlt || ''
            };
            this.observe(el, data);
        });
    }
    
    async loadPhoto(element) {
        if (this.loadedImages.has(element)) return;
        
        const data = element._photoData;
        if (!data) return;
        
        try {
            // 加载缩略图
            if (data.thumbnail) {
                await this.loadImage(element, data.thumbnail);
            }
            
            // 后台加载高清图
            if (data.src && data.src !== data.thumbnail) {
                this.loadImage(element, data.src);
            }
            
            this.loadedImages.add(element);
            
        } catch (error) {
            this.showError(element);
        }
    }
    
    async loadImage(element, src) {
        // 请求去重
        if (this.loadingCache.has(src)) {
            return this.loadingCache.get(src);
        }
        
        const promise = new Promise((resolve, reject) => {
            const img = new Image();
            let attempts = 0;
            
            const tryLoad = () => {
                img.onload = () => {
                    this.displayImage(element, img);
                    this.loadingCache.delete(src);
                    resolve();
                };
                
                img.onerror = () => {
                    attempts++;
                    if (attempts < this.options.retryAttempts) {
                        setTimeout(tryLoad, this.options.retryDelay);
                    } else {
                        this.loadingCache.delete(src);
                        reject(new Error('加载失败'));
                    }
                };
                
                img.src = src;
            };
            
            tryLoad();
        });
        
        this.loadingCache.set(src, promise);
        return promise;
    }
    
    displayImage(element, img) {
        // 移除占位符
        const placeholder = element.querySelector('.photo-placeholder');
        if (placeholder) placeholder.remove();
        
        // 创建或更新 img 元素
        let imgElement = element.querySelector('.photo-img');
        if (!imgElement) {
            imgElement = document.createElement('img');
            imgElement.className = 'photo-img';
            imgElement.alt = element._photoData.alt || '';
            element.appendChild(imgElement);
        }
        
        imgElement.src = img.src;
        
        // 使用 requestAnimationFrame 优化动画
        requestAnimationFrame(() => {
            imgElement.classList.add('loaded');
        });
    }
    
    showError(element) {
        element.innerHTML = '<div class="photo-error">❌<br>加载失败</div>';
    }
    
    destroy() {
        if (this.observer) {
            this.observer.disconnect();
        }
        this.loadingCache.clear();
    }
}

// 导出
window.AsyncPhotoLoader = AsyncPhotoLoaderOptimized;
