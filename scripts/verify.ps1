param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

python -B -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p)) for p in pathlib.Path('.').rglob('*.py')]"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if (-not $SkipTests) {
    python -B -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
