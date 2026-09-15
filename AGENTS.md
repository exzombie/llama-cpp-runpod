# AGENTS.md

RunPod serverless template that serves any Hugging Face GGUF model through llama.cpp's `llama-server` behind an OpenAI-compatible API. Published on RunPod Hub; the default branch is `master`.

## Verification

There are no tests, linters, or typecheckers. The only local check is `docker build .`; full behavior requires a GPU worker. `cd src && python handler.py --test` runs runpod's local test mode using `src/test_input.json` (needs a llama-server listening on port 3098).

## Gotchas

- Root `handler.py` is an intentionally empty marker file that only exists so RunPod's repo scanner detects a serverless endpoint. The real handler is `src/handler.py` — never "fix" or fill in the root file.
- Port 3098 is a hard contract: `src/start.sh` forces `--port 3098`, `src/engine.py` points its OpenAI client at `localhost:3098`, and `--port` in `LLAMA_SERVER_CMD_ARGS` is rejected.
- `src/start.sh`'s `fail()` sleeps 20s before exiting on purpose: config errors would otherwise exit before RunPod captures any container log. Don't remove the wait.
- Don't hand-edit the `FROM` digest in the `Dockerfile`; `.github/workflows/latest-llamacpp.yml` pins it automatically from the floating `llama.cpp:server-cuda` tag.

## Architecture

- `src/start.sh` is the container entrypoint: it resolves the model source (RunPod model cache via `find_cached.py`, a model baked into the image via `/models/baked.json` written by `src/fetch_model.py`, or `LLAMA_ARG_HF_REPO` + `LLAMA_HF_QUANT` merged into `repo:quant` syntax; cache > baked > download), launches `/app/llama-server`, polls `/health` with no timeout (large models download for minutes), then starts the RunPod handler.
- `docker build --build-arg LLAMA_ARG_HF_REPO=<hf-repo>` bakes a model into the image at build time (`src/fetch_model.py` downloads it into `/models` and writes the manifest).
- Almost all configuration flows as `LLAMA_ARG_*` env vars straight to llama-server; `start.sh` only does the glue above. Anything else is passed verbatim via `LLAMA_SERVER_CMD_ARGS`.
- `.runpod/hub.json` is the schema source of truth for the template UI. Config-surface changes touch `hub.json` and the README config table together.
- `catalog/generate.py` renders per-model Hub listing repos from `catalog/models.json`, reusing `hub.json` as schema. Its output is synced to the `runpod-serverless-templates` GitHub org by CI and is never edited by hand.

## Releases

Releases are named after the llama.cpp build in the pinned image (`b10975` style) and are cut automatically when llama.cpp publishes a new server image. Because RunPod Hub ignores moved tags, reused tags get `-2`/`-3` suffixes. When creating releases manually, check existing tags to avoid colliding with this scheme.
