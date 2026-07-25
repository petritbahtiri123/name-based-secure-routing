FROM python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 nbsr && useradd --uid 10001 --gid nbsr --no-create-home nbsr
COPY pyproject.toml .
COPY constraints/runtime.txt constraints/runtime.txt
COPY nbsr ./nbsr
RUN pip install --no-cache-dir --constraint constraints/runtime.txt .
USER 10001:10001
ENTRYPOINT ["uvicorn"]
