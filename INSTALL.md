# Install and run

Mushroom Spawn Run Analytics is a single-process Streamlit app with a local SQLite file.
Nothing is installed system-wide, nothing is downloaded at runtime and no environment
variables are required.

## Prerequisites

- Python 3.10 or newer (tested on 3.11) including `pip` and the `venv`-free system install
- ~150 MB of disk for the Python dependencies (Streamlit, pandas, Altair, pytest)

The only package manager used is `pip`, against the `requirements.txt` pins in the
repository root. There is no `package-lock.json`, no `yarn.lock`, no `node_modules`.

## 1. Install dependencies, create the schema and seed the demo data

```bash
sh install.sh
```

This runs, in order:

1. `python3 -m pip install --upgrade pip setuptools wheel`
2. `python3 -m pip install -r requirements.txt`
3. an import self-check of the app packages
4. `python3 seed.py` — creates `data/app.db` with the schema and the demo dataset
   (4 grow rooms, 6 strains, 14 bags, 51 readings, 31 flushes, 8 incidents,
   8 threshold rows, the demo user)

The script exits when it is done. It never starts the web server, never prompts, and
never runs `sudo`/`apt-get`.

## 2. Seed (its own step, safe to re-run)

`sh install.sh` already seeds, but the seed step is also available on its own:

```bash
python3 seed.py          # create schema + demo data if missing (idempotent)
python3 seed.py --reset  # wipe and reseed to identical counts
```

Seeding uses `core/seed.py`, which checks for existing rows and exits without starting
any server. The app itself also seeds on the normal boot path, so a fresh clone with no
`data/app.db` still boots into a populated workspace.

## 3. Run the app

```bash
streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true
```

or `sh start.sh`, which runs exactly that command. The server binds `0.0.0.0:8501`;
open http://localhost:8501 and sign in with the demo credential
(`cenius@cenius.ai` / `cenius`), which is also printed on the sign-in card.

## 4. Run the tests

```bash
python3 -m pytest -q
```

The suite uses `streamlit.testing.v1.AppTest` and a temporary SQLite file, so it does not
touch your `data/app.db`.

## Configuration (optional)

No `.env` file is needed. If you want to relocate the database, set one variable:

```bash
cp .env.example .env     # optional; the app boots with or without it
export MSRA_DB_PATH=./data/app.db
```

`MSRA_DB_PATH` is read once at import time with the project-relative default as fallback.
