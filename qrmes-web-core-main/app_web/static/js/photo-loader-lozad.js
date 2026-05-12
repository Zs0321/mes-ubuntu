/**
 * 基于 lozad.js 的照片加载器
 * 最轻量级方案 (1.1KB gzipped)
 * 
 * CDN: https://cdn.jsdelivr.net/npm/lozad@1.16.0/dist/lozad.min.js
 */

class PhotoLoaderLozad {
    constructor(options = {}) {
        this.options = {
            rootMargin: '100px',
            threshold: 0.01,
            loaded: (el) => this.onLoaded(el),
            ...options
        };
        
        this.observer = null;
        this.stats = {
            total: 0,
            loaded: 0,
            failed: 0
        };
    }
    
    async init() {
        // 动态加载 lozad.js
        if (typeof lozad === 'undefined') {
            await this.loadScript('https://cdn.jsdelivr.net/npm/lozad@1.16.0/dist/lozad.min.js');
        }
        
        // 初始化 lozad
        this.observer = lozad('.lazy-photo', {
            rootMargin: this.options.rootMargin,
            threshold: this.options.threshold,
            loaded: this.options.loaded
        });
        
        this.observer.observe();
        
        console.log('✅ Lozad 照片加载器已初始化');
    }
    
    loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    onLoaded(el) {
        el.classList.add('loaded');
        this.stats.loaded++;
        
        // 触发自定义事件
        const event = new CustomEvent('photoLoaded', {
            detail: {
                element: el,
                stats: this.stats
            }
        });
        document.dispatchEvent(event);
    }
    
    /**
     * 渲染照片网格
     */
    renderPhotoGrid(photos, container) {
        const grid = document.getElementById(container);
        grid.innerHTML = '';
        
        this.stats.total = photos.length;
        
        photos.forEach(photo => {
            const card = document.createElement('div');
            card.className = 'photo-card';
            card.innerHTML = `
                <div class="photo-wrapper">
                    <img class="lazy-photo" 
                         data-src="${photo.thumbnailUrl}"
                         data-placeholder-background="#f0f0f0"
                         alt="${photo.processStep}">
                </div>
                <div class="photo-info">
                    <h3>${photo.processStep}</h3>
                    <p>${photo.serialNumber}</p>
                </div>
            `;
            grid.appendChild(card);
        });
        
        // 重新观察新元素
        if (this.observer) {
            this.observer.observe();
        }
    }
    
    getStats() {
        return this.stats;
    }
}

// 导出
window.PhotoLoaderLozad = PhotoLoaderLozad;
