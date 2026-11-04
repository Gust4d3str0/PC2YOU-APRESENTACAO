import os
import subprocess


subprocess.run(["alembic", "upgrade", "head"], check=True)
os.execvp("uvicorn", ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"])
