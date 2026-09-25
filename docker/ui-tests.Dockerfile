# Runner for the Playwright and run_suite.py cases in automation-map.json.
#
# The Jenkins agent is Ubuntu 20.04 with python3.8, and Playwright needs >=3.10;
# deadsnakes has no 3.11 for focal. So the UI tests run in this image instead of
# on the agent's interpreter. The base ships the browsers at /ms-playwright but
# not the python bindings.
#
# requirements.txt is the UI repo's own, copied into this context by the
# pipeline before building. run_suite.py imports the application package
# (dotenv, neo4j, minio, ...), so pytest-only dependencies are not enough.
#
#   cp ../automation_fast_api/requirements.txt docker/
#   docker build -t quipu/ui-tests:1.63.0 -f docker/ui-tests.Dockerfile docker/
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

COPY requirements.txt /tmp/requirements.txt

# Install the repo's dependencies first, then re-pin playwright: requirements.txt
# leaves it unpinned, and a different version looks for browsers this image does
# not carry.
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
 && pip install --no-cache-dir --break-system-packages \
      playwright==1.63.0 pytest pytest-playwright \
 && rm /tmp/requirements.txt
