FROM ollama/ollama:latest

ARG OLLAMA_MODEL=qwen2.5:3b-instruct
ENV OLLAMA_MODEL=${OLLAMA_MODEL}

RUN ollama serve & \
    server_pid=$!; \
    tries=0; \
    until ollama list >/dev/null 2>&1; do \
      tries=$((tries + 1)); \
      if [ "$tries" -gt 60 ]; then \
        echo "ollama server did not become ready in time" >&2; \
        exit 1; \
      fi; \
      sleep 1; \
    done; \
    ollama pull "${OLLAMA_MODEL}"; \
    kill "$server_pid"

EXPOSE 11434
ENTRYPOINT ["ollama", "serve"]
