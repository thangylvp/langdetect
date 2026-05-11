# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`langdetect` is a language detection micromodule embedded in the `robot-agent-gateway` monorepo. It detects whether input text is English (`EN`), Vietnamese (`VI`), or `UNKNOWN`, and is exposed as a FastAPI router mounted at `/api/v2/langdetect`.

## Architecture

The module has four layers:

- **[detector.py](detector.py)** — Abstract base class `LanguageDetector` with two concrete implementations:
  - `LinguaDetector` (default): uses `lingua-language-detector`, falls back to `VI` when confidence < 0.5
  - `FastTextDetector`: loads the binary model at `FASTTEXT_MODEL_PATH`, patches NumPy 2.x compatibility at import time
- **[service.py](service.py)** — `@lru_cache` singletons so detectors are initialized once per process; `detect(text, engine)` returns `(Language, float)`
- **[schemas.py](schemas.py)** — Pydantic `DetectRequest` / `DetectResponse` models and `DetectorEngine` enum
- **[router.py](router.py)** — Single `POST /langdetect/detect` endpoint; the parent app mounts it with the `/api/v2` prefix

The FastText binary model lives at [models/lid.176.ftz](models/lid.176.ftz) and is only loaded when `engine=fasttext` is requested.

## Running the service

This module has no standalone entrypoint. It runs as part of the gateway:

```bash
# From the monorepo root
cd packages/gateway
uvicorn backend.main:app --reload
```

Or via Docker Compose (from the gateway package directory):

```bash
docker compose up --build
```

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `FASTTEXT_MODEL_PATH` | Only for FastText engine | Path to `lid.176.ftz` binary model |

## Dependencies

Declared in the parent `pyproject.toml`:
- `lingua-language-detector>=2.0.2`
- `fasttext-langdetect>=1.0.5` (optional, only needed for FastText engine)

## No tests

There are currently no automated tests for this module.
