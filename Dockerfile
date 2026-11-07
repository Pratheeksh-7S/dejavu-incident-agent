# DejaVu on Hugging Face Spaces: Hindsight memory server + Streamlit app in one container.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Spaces run as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HINDSIGHT_BASE_URL=http://localhost:8888 \
    HINDSIGHT_API_LLM_PROVIDER=groq \
    HINDSIGHT_API_LLM_MODEL=openai/gpt-oss-120b \
    HINDSIGHT_API_LLM_GROQ_SERVICE_TIER=on_demand
WORKDIR /home/user/app

# CPU-only torch keeps the image small (Spaces free hardware has no GPU)
RUN pip install --no-cache-dir --user torch --index-url https://download.pytorch.org/whl/cpu
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user . .

EXPOSE 7860
CMD ["bash", "hf_start.sh"]
