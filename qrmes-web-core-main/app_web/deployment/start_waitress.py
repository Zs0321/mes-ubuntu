"""
Waitress WSGI服务器启动脚本 - Windows Server 2016
用于生产环境部署QRTestScanner MES应用
"""
import logging
import sys
from pathlib import Path
from waitress import serve

# 配置日志
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'waitress.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def main():
    """启动Waitress服务器"""
    try:
        # 导入Flask应用
        from mesapp import app
        
        logger.info("=" * 60)
        logger.info("QRTestScanner MES Application - Waitress Server")
        logger.info("=" * 60)
        logger.info("Environment: Windows Server 2016")
        logger.info("Server: Waitress WSGI Server")
        logger.info("Listening on: http://127.0.0.1:8891")
        logger.info("Threads: 8")
        logger.info("=" * 60)
        logger.info("Press Ctrl+C to stop (or use Windows Service)")
        logger.info("")
        
        # 启动Waitress服务器
        serve(
            app,
            host='127.0.0.1',      # 仅监听本地，通过IIS对外提供服务
            port=8891,             # 端口号
            threads=8,             # 工作线程数，根据CPU核心数调整
            channel_timeout=120,   # 通道超时时间(秒)
            cleanup_interval=30,   # 清理间隔(秒)
            connection_limit=1000, # 最大连接数
            asyncore_use_poll=True,# 使用poll而不是select (Windows兼容性)
        )
        
    except KeyboardInterrupt:
        logger.info("\n" + "=" * 60)
        logger.info("Server stopped by user (Ctrl+C)")
        logger.info("=" * 60)
    except Exception as e:
        logger.error("=" * 60)
        logger.error("Server error occurred!")
        logger.error(f"Error: {e}", exc_info=True)
        logger.error("=" * 60)
        raise

if __name__ == '__main__':
    main()
