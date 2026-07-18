FROM python:3.12.10-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --gid 10001 nbsr && useradd --uid 10001 --gid nbsr --no-create-home nbsr
COPY pyproject.toml .
COPY nbsr ./nbsr
RUN pip install --no-cache-dir .
USER 10001:10001
ENTRYPOINT ["uvicorn"]
