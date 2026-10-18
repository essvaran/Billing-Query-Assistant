# Windows equivalent of the Makefile.  Usage:  ./tasks.ps1 <task> [ticket id]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("up", "setup", "corpus", "ingest", "seed", "demo", "answer", "eval", "test", "smoke", "mcp-http", "api")]
    [string]$Task,
    [string]$Ticket = "TK3001"
)
$py = if ($env:PY) { $env:PY } else { "python" }

switch ($Task) {
    "up"     { & $py -m tier1 up }
    "setup"  { & $py -m pip install -r requirements.txt }
    "corpus" { & $py scripts/generate_synthetic_corpus.py }
    "ingest" { & $py scripts/generate_synthetic_corpus.py; & $py scripts/ingest_variant_a.py }
    "seed"   { & $py -m tier1 seed }
    "demo"   { & $py -m tier1 demo }
    "answer" { & $py -m tier1 answer --ticket $Ticket }
    "eval"   { & $py -m tier1 eval }
    "test"   { & $py -m pytest tests -q }
    "smoke"  { & $py scripts/mcp_smoke.py }
    "mcp-http" { & $py mcp_servers/help_centre_server.py --transport http }
    "api"    { & $py -m uvicorn api.main:app --port 8000 }
}
