# Runner for the Playwright cases in automation-map.json.
#
# The Jenkins agent is Ubuntu 20.04 with python3.8, and Playwright needs >=3.10;
# deadsnakes has no 3.11 for focal. So the UI tests run in this image instead of
# on the agent's interpreter. The base ships the browsers at /ms-playwright but
# not the python bindings, which is all this adds.
#
#   docker build -t quipu/ui-tests:1.63.0 -f docker/ui-tests.Dockerfile docker/
#
# Keep the playwright pin equal to the base image tag; a mismatch makes the
# bindings download a second browser set at run time.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

RUN pip install --no-cache-dir --break-system-packages \
      playwright==1.63.0 pytest pytest-playwright
