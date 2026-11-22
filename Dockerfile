# My Tesla 标准容器镜像: 纯 Python 后端 + 静态前端 (无构建步骤),
# 运行期只需要 app/ 与 requirements.txt。参数与 env 跟 README「3.2
# 手动运行」里的 `python -m app` 完全同一套。
FROM python:3.13-slim

LABEL org.opencontainers.image.title="My Tesla" \
      org.opencontainers.image.description="TeslaMate 可视化工具" \
      org.opencontainers.image.source="https://github.com/kinopico-zhang/my-tesla" \
      org.opencontainers.image.licenses="MIT"

# 不写 .pyc、日志不缓冲 (docker logs 实时可见)、不留 pip 缓存
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

# 库内存 UTC 裸时间戳, 对外按这个时区渲染 (TZ 给 glibc, TZ_NAME 给应用)
ENV TZ=Asia/Shanghai \
    TZ_NAME=Asia/Shanghai

# 运行期唯一的可写处是 /app/data: 两个 SQLite 库、缓存, 以及会话密钥
# (默认会落在 /app 根上, 改到 data/ 里就只有一个卷要挂)
ENV MYHOME_SECRET_FILE=/app/data/.session_secret

WORKDIR /app

# 依赖单独一层: 只改应用代码时不重装依赖
COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app

# 非 root 运行 (uid 1000): 宿主上 data/ 的属主对齐成 1000 即可直接写
RUN useradd --create-home --uid 1000 mytesla \
    && mkdir -p /app/data \
    && chown -R mytesla:mytesla /app/data
USER mytesla

EXPOSE 8500

# 健康探针打公开路径 /login (不需要会话): 200 即服务在响应。
# start-period 给首启建库 (SQLite 建表 + 迁移) 留出时间。
# 用应用自己的解释器 + 标准库 urllib, 不必为探针额外装 curl。
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/login', timeout=4)"]

# 必须听 0.0.0.0 才能穿透容器网络; 宿主端口由 compose 映射
CMD ["python", "-m", "app", "--host", "0.0.0.0", "--port", "8500"]
