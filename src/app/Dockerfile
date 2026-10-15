FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --group dashboard

COPY src/app/dash.py .

CMD ["uv", "run", "--frozen", "--no-dev", "--group", "dashboard", "streamlit", "run", "dash.py", "--server.port=8501", "--server.address=0.0.0.0"]