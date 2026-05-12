/**
 * 基于 lazysizes 的照片加载器
 * 最流行的懒加载库 (11k+ stars)
 * 
 * CDN: https://cdn.jsdelivr.net/npm/lazysizes@5.3.2/lazysizes.min.js
 * 
 * 特点:
 * - 零配置，自动检测
 * - 支持 IE9+
 * - 自动响应式图片
 * - 插件生态丰富
 */

class PhotoLoaderLazySizes {
    constructor(options = {}) {
        this.options = {
            lazyClass: 'lazyload',
            loadingClass: 'lazyloading',
            loadedClass: 'lazyloaded',
            ...options
        };
        
        this.stats = {
            total: 0,
            loaded: 0,
            failed: 0
        };
    }
    
    async init() {
        // 配置 lazysizes
        window.lazySizesConfig = window.lazySizesConfig || {};
        window.lazySizesConfig.lazyClass = this.options.lazyClass;
        window.lazySizesConfig.loadingClass = this.options.loadingClass;
        window.lazySizesConfig.loadedClass = this.options.loadedClass;
        window.lazySizesConfig.expand = 100; // 提前 100px 加载
        
        // 动态加载 lazysizes
        if (typeof lazySizes === 'undefined') {
            await this.loadScript('https://cdn.jsdelivr.net/npm/lazysizes@5.3.2/lazysizes.min.js');
        }
        
        // 监听加载事件
        document.addEventListener('lazyloaded', (e) => {
            this.onLoaded(e.target);
        });
        
        document.addEventListener('lazyerror', (e) => {
            this.onError(e.target);
        });
        
        console.log('✅ LazySizes 照片加载器已初始化');
    }
    
    loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.async = true;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    onLoaded(el) {
        this.stats.loaded++;
        
        // 添加淡入动画
        el.style.opacity = '0';
        setTimeout(() => {
            el.style.transition = 'opacity 300ms';
            el.style.opacity = '1';
        }, 10);
        
        // 触发事件
        const event = new CustomEvent('photoLoaded', {
            detail: { element: el, stats: this.stats }
        });
        document.dispatchEvent(event);
    }
    
    onError(el) {
        this.stats.failed++;
        
        // 显示错误占位符
        el.parentElement.innerHTML = `
            <div class="photo-error">
                <div>❌</div>
                <div>加载失败</div>
            </div>
        `;
    }
    
    /**
     * 渲染照片网格（支持响应式图片）
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
                    <!-- 响应式图片 -->
                    <img class="lazyload" 
                         data-src="${photo.thumbnailUrl}"
                         data-srcset="${photo.thumbnailUrl} 300w, ${photo.fullUrl} 1200w"
                         data-sizes="auto"
                         alt="${photo.processStep}">
                </div>
                <div class="photo-info">
                    <h3>${photo.processStep}</h3>
                    <p>${photo.serialNumber}</p>
                </div>
            `;
            grid.appendChild(card);
        });
    }
    
    /**
     * 手动触发加载（用于动态内容）
     */
    update() {
        if (typeof lazySizes !== 'undefined') {
            lazySizes.autoSizer.checkElems();
        }
    }
    
    getStats() {
        return this.stats;
    }
}

// 导出
window.PhotoLoaderLazySizes = PhotoLoaderLazySizes;
