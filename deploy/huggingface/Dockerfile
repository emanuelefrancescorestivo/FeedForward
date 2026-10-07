# The public demo of FeedForward on a Hugging Face Space (Docker).
# deploy.py copies this file to the Space's root next to backend/, the licences
# and README.md (the Space card). The database is SQLite inside the container:
# it is wiped whenever the Space restarts, which suits a demo.
FROM python:3.12-slim

# CBC (the solver PuLP calls to plan a week) needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

# Spaces run the container as user 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1
WORKDIR /home/user/app

# the app's libraries, without the test tools (pytest, playwright)
COPY --chown=user backend/requirements.txt requirements.txt
RUN grep -v -E "^(pytest|playwright)" requirements.txt > run.txt && pip install --no-cache-dir --user -r run.txt

COPY --chown=user backend/ .

# demo: a fresh account per visitor, no name sign-in; FEEDFORWARD_SECRET is a Space secret
ENV FEEDFORWARD_ENV=demo FEEDFORWARD_DATABASE_URL=sqlite:////home/user/feedforward-demo.db
EXPOSE 7860
# --proxy-headers: the request limit counts each visitor, not the Space's proxy
CMD ["uvicorn", "feedforward.api.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]
