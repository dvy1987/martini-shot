# Martini Shot (codename post-command) — CI-lite (constitution C-3, plan task F-3)
# GNU Make 4.05+ (uses .RECIPEPREFIX so recipes survive Windows editors)
.RECIPEPREFIX := >

.PHONY: install hooks lint typecheck test eval-check integrity harness-check check

install:            ## Install dev toolchain (backend + tooling)
>python -m pip install -r requirements-dev.txt

hooks:              ## Install pre-commit hooks (ruff, secret scan, integrity)
>python -m pre_commit install

lint:               ## Ruff lint + format check
>python -m ruff check backend scripts tests
>python -m ruff format --check backend scripts tests

typecheck:          ## Mypy on backend
>python -m mypy backend

test:               ## Unit + integration harness
>python -m pytest tests -q

eval-check:         ## Eval thresholds structure gate (constitution C-3.4)
>python backend/evals/check_thresholds.py

integrity:          ## Constitution C-1.2 no-mocks/stubs grep over product code
>python scripts/integrity_check.py

harness-check:      ## Harness manifest drift gate (docs/harness/)
>python docs/harness/drift_check.py

check: lint typecheck test eval-check integrity harness-check  ## Full CI-lite gate
