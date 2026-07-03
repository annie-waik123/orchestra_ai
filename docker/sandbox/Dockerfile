FROM python:3.13-slim

WORKDIR /workspace

# Pre-install pinned runtime dependencies for validating generated code
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    pydantic==2.9.2 \
    sqlalchemy==2.0.35 \
    httpx==0.27.2 \
    uvicorn==0.30.6

# Make workspace readable and executable
RUN chmod -R 777 /workspace

CMD ["python", "-c", "print('Orchestra AI Sandbox ready')"]
