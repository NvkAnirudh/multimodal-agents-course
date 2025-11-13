CHECK_DIRS := .

# --- Ruff ---

format-fix:
	uv run ruff format $(CHECK_DIRS) 
	uv run ruff check --select I --fix

lint-fix:
	uv run ruff check --fix

format-check:
	uv run ruff format --check $(CHECK_DIRS) 
	uv run ruff check -e
	uv run ruff check --select I -e

lint-check:
	uv run ruff check $(CHECK_DIRS)

# --- MCP Server ---

start-recollect-mcp: stop-recollect-mcp
	docker build -t recollect-mcp . && \
	docker run -it -p 9090:9090 --name recollect-mcp --env-file .env -v ./notebooks/data:/app/videos -v ./.pixeltable:/root/.pixeltable -v ./.records:/app/.records -v ~/.cache/huggingface:/root/.cache/huggingface recollect-mcp

inspect-recollect-mcp:
	curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash && \
	. ~/.nvm/nvm.sh && \
	nvm install node; \
	npx @modelcontextprotocol/inspector

stop-recollect-mcp:
	docker stop recollect-mcp || true && \
	docker rm recollect-mcp || true && \
	rm -rf .pixeltable && \
	rm -rf .records

# --- FFmpeg ---

fix-video:
	ffmpeg -i $(input) -c:v libx264 -c:a copy $(output)

