FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY main.py ./

ENV APP_HOST=0.0.0.0
ENV APP_PORT=8000
ENV APP_RELOAD=false

EXPOSE 8000

CMD ["uv", "run", "python", "main.py"]
