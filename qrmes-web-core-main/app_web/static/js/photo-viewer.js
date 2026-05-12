/**
 * 照片查看器 - 支持全屏、缩放、拖拽
 * 类似于 Windows 照片查看器的功能
 */

class PhotoViewer {
    constructor() {
        this.currentPhoto = null;
        this.scale = 1;
        this.minScale = 0.1;
        this.maxScale = 5;
        this.translateX = 0;
        this.translateY = 0;
        this.rotation = 0;
        this.isDragging = false;
        this.startX = 0;
        this.startY = 0;
        this.isFullscreen = false;
        
        this.init();
    }
    
    init() {
        // 创建查看器容器
        const viewer = document.createElement('div');
        viewer.id = 'photoViewer';
        viewer.className = 'photo-viewer';
        viewer.style.display = 'none';
        viewer.innerHTML = `
            <div class="photo-viewer-overlay"></div>
            <div class="photo-viewer-container">
                <div class="photo-viewer-toolbar">
                    <button class="viewer-btn" id="viewerZoomIn" title="放大 (滚轮向上)">
                        <i class="bi bi-zoom-in"></i>
                    </button>
                    <button class="viewer-btn" id="viewerZoomOut" title="缩小 (滚轮向下)">
                        <i class="bi bi-zoom-out"></i>
                    </button>
                    <button class="viewer-btn" id="viewerReset" title="重置 (双击)">
                        <i class="bi bi-arrow-counterclockwise"></i>
                    </button>
                    <button class="viewer-btn" id="viewerRotate" title="顺时针旋转 90° (R)">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                    <button class="viewer-btn" id="viewerFullscreen" title="全屏 (F)">
                        <i class="bi bi-fullscreen"></i>
                    </button>
                    <span class="viewer-zoom-level">100%</span>
                    <button class="viewer-btn viewer-close" id="viewerClose" title="关闭 (ESC)">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
                <div class="photo-viewer-content">
                    <img id="viewerImage" src="" alt="照片">
                </div>
                <div class="photo-viewer-info">
                    <div id="viewerFileName"></div>
                    <div id="viewerImageSize"></div>
                </div>
            </div>
        `;
        document.body.appendChild(viewer);
        
        // 绑定事件
        this.bindEvents();
    }
    
    bindEvents() {
        const viewer = document.getElementById('photoViewer');
        const image = document.getElementById('viewerImage');
        const content = document.querySelector('.photo-viewer-content');
        
        // 工具栏按钮
        document.getElementById('viewerZoomIn').addEventListener('click', () => this.zoomIn());
        document.getElementById('viewerZoomOut').addEventListener('click', () => this.zoomOut());
        document.getElementById('viewerReset').addEventListener('click', () => this.reset());
        document.getElementById('viewerRotate').addEventListener('click', () => this.rotateClockwise());
        document.getElementById('viewerFullscreen').addEventListener('click', () => this.toggleFullscreen());
        document.getElementById('viewerClose').addEventListener('click', () => this.close());
        
        // 点击遮罩层关闭
        document.querySelector('.photo-viewer-overlay').addEventListener('click', () => this.close());
        
        // 鼠标滚轮缩放
        content.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.deltaY < 0) {
                this.zoomIn();
            } else {
                this.zoomOut();
            }
        });
        
        // 鼠标拖拽
        image.addEventListener('mousedown', (e) => {
            if (this.scale > 1) {
                this.isDragging = true;
                this.startX = e.clientX - this.translateX;
                this.startY = e.clientY - this.translateY;
                image.style.cursor = 'grabbing';
            }
        });
        
        document.addEventListener('mousemove', (e) => {
            if (this.isDragging) {
                this.translateX = e.clientX - this.startX;
                this.translateY = e.clientY - this.startY;
                this.updateTransform();
            }
        });
        
        document.addEventListener('mouseup', () => {
            if (this.isDragging) {
                this.isDragging = false;
                image.style.cursor = this.scale > 1 ? 'grab' : 'default';
            }
        });
        
        // 双击重置
        image.addEventListener('dblclick', () => this.reset());
        
        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            if (viewer.style.display === 'flex') {
                switch(e.key) {
                    case 'Escape':
                        this.close();
                        break;
                    case 'f':
                    case 'F':
                        this.toggleFullscreen();
                        break;
                    case '+':
                    case '=':
                        this.zoomIn();
                        break;
                    case '-':
                    case '_':
                        this.zoomOut();
                        break;
                    case '0':
                        this.reset();
                        break;
                    case 'r':
                    case 'R':
                        this.rotateClockwise();
                        break;
                }
            }
        });
        
        // 全屏变化监听
        document.addEventListener('fullscreenchange', () => {
            this.isFullscreen = !!document.fullscreenElement;
            this.updateFullscreenButton();
        });
    }
    
    open(photoUrl, fileName, fileSize) {
        this.currentPhoto = {
            url: photoUrl,
            fileName: fileName,
            fileSize: fileSize
        };
        
        const viewer = document.getElementById('photoViewer');
        const image = document.getElementById('viewerImage');
        
        // 显示查看器
        viewer.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        
        // 加载图片
        image.src = photoUrl;
        image.onload = () => {
            // 显示图片信息
            document.getElementById('viewerFileName').textContent = fileName;
            document.getElementById('viewerImageSize').textContent = 
                `${image.naturalWidth} × ${image.naturalHeight} px`;
            
            // 重置变换
            this.reset();
        };
        
        image.onerror = () => {
            alert('图片加载失败');
            this.close();
        };
    }
    
    close() {
        const viewer = document.getElementById('photoViewer');
        viewer.style.display = 'none';
        document.body.style.overflow = '';
        
        // 退出全屏
        if (this.isFullscreen && document.fullscreenElement) {
            document.exitFullscreen();
        }
        
        // 重置状态
        this.reset();
        this.currentPhoto = null;
    }
    
    zoomIn() {
        this.scale = Math.min(this.scale * 1.2, this.maxScale);
        this.updateTransform();
        this.updateZoomLevel();
    }
    
    zoomOut() {
        this.scale = Math.max(this.scale / 1.2, this.minScale);
        this.updateTransform();
        this.updateZoomLevel();
    }
    
    reset() {
        this.scale = 1;
        this.translateX = 0;
        this.translateY = 0;
        this.rotation = 0;
        this.updateTransform();
        this.updateZoomLevel();
    }

    rotateClockwise() {
        this.rotation = (this.rotation + 90) % 360;
        this.updateTransform();
        this.updateZoomLevel();
    }
    
    updateTransform() {
        const image = document.getElementById('viewerImage');
        image.style.transform = `translate(${this.translateX}px, ${this.translateY}px) scale(${this.scale}) rotate(${this.rotation}deg)`;
        image.style.cursor = this.scale > 1 ? 'grab' : 'default';
    }
    
    updateZoomLevel() {
        const zoomLevel = document.querySelector('.viewer-zoom-level');
        zoomLevel.textContent = `${Math.round(this.scale * 100)}% · ${this.rotation}°`;
    }
    
    toggleFullscreen() {
        const viewer = document.getElementById('photoViewer');
        
        if (!this.isFullscreen) {
            if (viewer.requestFullscreen) {
                viewer.requestFullscreen();
            } else if (viewer.webkitRequestFullscreen) {
                viewer.webkitRequestFullscreen();
            } else if (viewer.msRequestFullscreen) {
                viewer.msRequestFullscreen();
            }
        } else {
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
        }
    }
    
    updateFullscreenButton() {
        const btn = document.getElementById('viewerFullscreen');
        const icon = btn.querySelector('i');
        if (this.isFullscreen) {
            icon.className = 'bi bi-fullscreen-exit';
            btn.title = '退出全屏 (F)';
        } else {
            icon.className = 'bi bi-fullscreen';
            btn.title = '全屏 (F)';
        }
    }
}

// 全局实例
let photoViewer = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('初始化照片查看器...');
    photoViewer = new PhotoViewer();
    console.log('照片查看器初始化完成');
});

// 全局函数：打开照片查看器
window.openPhotoViewer = function(photoUrl, fileName, fileSize) {
    console.log('openPhotoViewer 被调用:', photoUrl);
    
    // 如果 photoViewer 还未初始化，立即初始化
    if (!photoViewer) {
        console.log('photoViewer 未初始化，立即初始化');
        photoViewer = new PhotoViewer();
    }
    
    if (photoViewer && typeof photoViewer.open === 'function') {
        photoViewer.open(photoUrl, fileName, fileSize);
    } else {
        console.error('photoViewer.open 不是函数:', photoViewer);
        alert('照片查看器初始化失败，请刷新页面重试');
    }
};
