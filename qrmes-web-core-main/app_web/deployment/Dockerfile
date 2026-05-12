# 使用 Python 3.11 作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（强制使用清华 TUNA 源）
RUN set -eux; \
    # 清理默认源配置，避免访问 deb.debian.org / security.debian.org
    rm -f /etc/apt/sources.list.d/* || true; \
    # 根据当前 Debian 版本写入 TUNA 源
    . /etc/os-release; \
    echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian ${VERSION_CODENAME} main contrib non-free non-free-firmware" > /etc/apt/sources.list; \
    echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian ${VERSION_CODENAME}-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list; \
    echo "deb http://mirrors.tuna.tsinghua.edu.cn/debian-security ${VERSION_CODENAME}-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y \
        gcc \
        g++ \
        curl \
        libsmbclient-dev \
        libsmbclient \
        cifs-utils; \
    rm -rf /var/lib/apt/lists/*

# 复制 requirements.txt
COPY requirements.txt .

# 安装 Python 依赖（使用清华 PyPI 镜像加速）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt \
    && pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple \
        redis \
        gunicorn \
        gevent

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/data/databases \
    /app/data/logs \
    /app/data/cache \
    /app/data/config \
    /app/nas-mount/qrmes

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=mesapp.py
ENV FLASK_ENV=production

# 暴露端口
EXPOSE 5001

# 健康检查端点（需要在 mesapp.py 中添加）
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5001/health || exit 1

# 使用 Gunicorn 启动应用（生产环境）
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5001", \
     "--workers", "4", \
     "--worker-class", "gevent", \
     "--worker-connections", "1000", \
     "--timeout", "120", \
     "--access-logfile", "/app/data/logs/gunicorn-access.log", \
     "--error-logfile", "/app/data/logs/gunicorn-error.log", \
     "--log-level", "info", \
     "mesapp:app"]

# 开发环境启动方式（可以通过 docker-compose.override.yml 覆盖）
# CMD ["python", "mesapp.py"]
