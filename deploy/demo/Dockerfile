# The public demo of FeedForward (DECISIONS.md, decision 32), built by Cloud Run.
# deploy.py copies this file next to backend/ and the licences. The database is
# SQLite inside the container: it is wiped whenever the instance stops, which
# suits a demo (it asks for made-up details).
FROM python:3.12-slim

# CBC (the solver PuLP calls to plan a week) needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 app
USER app
ENV HOME=/home/app PATH=/home/app/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/app/feedforward

# the app's libraries, without the test tools (pytest, playwright)
COPY --chown=app backend/requirements.txt requirements.txt
RUN grep -v -E "^(pytest|playwright)" requirements.txt > run.txt && pip install --no-cache-dir --user -r run.txt

COPY --chown=app backend/ .

# demo: a fresh account per visitor, no name sign-in; FEEDFORWARD_SECRET comes from the deploy
ENV FEEDFORWARD_ENV=demo FEEDFORWARD_DATABASE_URL=sqlite:////home/app/feedforward-demo.db
# Cloud Run gives the port in $PORT; --proxy-headers: the request limit counts each visitor, not Google's proxy
CMD exec uvicorn feedforward.api.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips "*"
