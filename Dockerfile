ARG PRIVACY_MODEL_SOURCE=download
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY prototype/requirements.lock.txt /app/prototype/requirements.lock.txt
RUN python -m pip install -r prototype/requirements.lock.txt && python -m pip check
COPY prototype/__init__.py /app/prototype/__init__.py
COPY prototype/privacy_core /app/prototype/privacy_core
ENV PRIVACY_MODELS_DIR=/opt/privacy-models

FROM runtime AS models-download
RUN python -m prototype.privacy_core.prepare --dir /opt/privacy-models

# Optional verified public artifacts for a machine with no access to the CDN.
# These exact files are the only extra build-context entries; no private tree.
FROM runtime AS models-local
COPY runtime/privacy-models/slovnet_ner_news_v1.tar runtime/privacy-models/navec_news_v1_1B_250K_300d_100q.tar /opt/privacy-models/
RUN python -c "from prototype.privacy_core.models import load; load('/opt/privacy-models')"

FROM models-${PRIVACY_MODEL_SOURCE} AS final
COPY prototype/__main__.py prototype/contracts.py prototype/demo.py prototype/documents.py prototype/model.py prototype/pipeline.py prototype/privacy.py prototype/scoring.py prototype/application.py prototype/errors.py prototype/presentation.py prototype/evidence.py prototype/requirements_review.py /app/prototype/
COPY prototype/analysis_contracts.py prototype/candidate_profile.py prototype/ranking_explanation.py prototype/review_queue.py prototype/review_policy.py prototype/run_store.py prototype/local_service.py prototype/web_app.py /app/prototype/
COPY prototype/static /app/prototype/static
COPY scripts/privacy_smoke.py /app/scripts/privacy_smoke.py
COPY prototype/tests/test_core.py /app/prototype/tests/test_core.py
COPY prototype/tests/test_integrated_analysis.py prototype/tests/test_run_store.py prototype/tests/test_local_service.py prototype/tests/test_web_app.py /app/prototype/tests/
RUN python -m unittest discover -s prototype/tests -p 'test_core.py' -v \
    && python -m unittest prototype.tests.test_integrated_analysis prototype.tests.test_run_store prototype.tests.test_local_service prototype.tests.test_web_app -q \
    && python scripts/privacy_smoke.py --models-dir /opt/privacy-models \
    && python scripts/privacy_smoke.py --models-dir /opt/privacy-models --model-mock \
    && mkdir -p /app/data/private/prototype-runs \
    && chown -R 10001:10001 /app/data
USER 10001:10001
EXPOSE 8765
ENTRYPOINT ["python", "-m", "prototype"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765", "--state-dir", "/app/data/private/local-app"]
