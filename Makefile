# Tier-1 Deflection Assistant. One command per job. On Windows use tasks.ps1.
PY ?= python

.PHONY: up setup corpus ingest seed demo answer test smoke mcp-http api eval

up:               ## ONE command from a fresh clone: checks .env, installs, builds data and index, answers a ticket
	$(PY) -m tier1 up

setup:            ## install dependencies
	$(PY) -m pip install -r requirements-dev.txt

corpus:           ## generate the SYNTHETIC corpus (deterministic)
	$(PY) scripts/generate_synthetic_corpus.py

ingest: corpus    ## build the Tier-1 vector collection
	$(PY) scripts/ingest_variant_a.py

seed:             ## load synthetic customers, orders, tickets into data/tier1.db
	$(PY) -m tier1 seed

demo:             ## answer a RANDOM ticket (seed is printed so the draw can be reproduced)
	$(PY) -m tier1 demo

answer:           ## make answer TICKET=TK3001
	$(PY) -m tier1 answer --ticket $(TICKET)

test:             ## unit and integration tests (no network needed except MCP subprocesses)
	$(PY) -m pytest tests -q

smoke:            ## talk to both MCP servers the way an outside client would
	$(PY) scripts/mcp_smoke.py

eval:             ## the integrated eval suite (resumable: make eval ARGS="--tag fix1 --resume")
	$(PY) -m tier1 eval $(ARGS)

mcp-http:         ## serve the help-centre MCP server over HTTP on :8765 (needs MCP_HTTP_TOKEN in .env)
	$(PY) mcp_servers/help_centre_server.py --transport http

api:              ## start the API
	$(PY) -m uvicorn api.main:app --port 8000
