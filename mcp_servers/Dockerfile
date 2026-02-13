FROM python:3.11-slim

ARG TOOL_DIR

WORKDIR /app

COPY ${TOOL_DIR}/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ${TOOL_DIR}/ .

ENV MCP_HOST=0.0.0.0
ENV MCP_TRANSPORT=streamable-http

CMD ["python", "server.py"]
