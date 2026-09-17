.PHONY: install run run-windows test clean

install:
	pip install -r trading-agent/requirements.txt
	cd trading-agent/logging_observability/dashboard/frontend && npm install

run:
	bash trading-agent/start_agent.sh

run-windows:
	trading-agent\start_agent.bat

test:
	PYTHONPATH=trading-agent pytest trading-agent/tests

clean:
	python -c "import os, shutil; [shutil.rmtree(os.path.join(r, d), ignore_errors=True) for r, ds, fs in os.walk('.') if not any(x in r for x in ('node_modules', '.git', 'venv', '.venv')) for d in list(ds) if d in ('__pycache__', '.pytest_cache')]; [os.remove(os.path.join(r, f)) for r, ds, fs in os.walk('.') if not any(x in r for x in ('node_modules', '.git', 'venv', '.venv')) for f in fs if f.endswith(('.pyc', '.pyo'))]"
