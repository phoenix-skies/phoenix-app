# phoenix-app

Source code, tests and CI for **Project Phoenix**, the e-commerce platform DataQuaint is building for Phoenix Electronics.

| Path | What it is |
|---|---|
| `frontend/` | Storefront (static HTML/JS served by nginx; `/api` is proxied to the product API) |
| `backend/` | Product API (Flask): products, cart, `/healthz`, `/readyz`, `/metrics` |
| `tests/` | Unit tests (pytest) |
| `Dockerfile` | Product API image |
| `frontend/Dockerfile` | Storefront image |
| `.github/workflows/ci.yml` | Test → build → Trivy scan → push to GHCR → PR to `phoenix-gitops` |

The database (PostgreSQL) is deployed from the GitOps repo, so it isn't built here.

## Run locally

```bash
pip install -r requirements-dev.txt
pytest -v tests                       # 9 tests
cd backend && python app.py           # API on :8080 using SQLite
```

With Docker:

```bash
docker build -t phoenix-backend .
docker build -t phoenix-frontend frontend
docker network create phoenix
docker run -d --name phoenix-backend --network phoenix phoenix-backend
docker run -d -p 8081:8080 --network phoenix phoenix-frontend
# open http://localhost:8081
```

## Environment variables (backend)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | *(empty → SQLite)* | `postgresql://user:pass@host:5432/db` |
| `APP_VERSION` | `dev` | Shown in UI and metrics; CI sets it to the image tag |
| `ERROR_RATE` | `0` | Fraction of product requests that return 500. Used to simulate a bad canary |

## How CI connects to GitOps

1. A push to `main` runs the tests, builds both images and scans them with Trivy.
2. The images are pushed as `ghcr.io/<org>/phoenix-<component>:sha-<7chars>`, and CI records the digest.
3. CI opens a PR on `phoenix-gitops` that sets `values-dev.yaml` to `sha-xxxxxxx@sha256:…`, an immutable reference.
4. When someone merges that PR, Argo CD syncs **dev**. QA and prod are promoted by PR in the GitOps repo.

**One-time setup:** add the `GITOPS_TOKEN` secret (see the workflow header). After the first push, make both GHCR packages **public**, or add an imagePullSecret.
