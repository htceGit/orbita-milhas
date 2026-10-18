FROM python:3.12-slim-bookworm
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
WORKDIR /app
COPY calendar_service/requirements.lock calendar_service/requirements.lock
RUN pip install --no-cache-dir -r calendar_service/requirements.lock && python -m playwright install --with-deps chromium && chmod -R a+rX /opt/ms-playwright && useradd --create-home orbita
COPY worker worker
COPY fare-policy.json fare-policy.json
COPY calendar_service calendar_service
USER orbita
EXPOSE 8080
CMD ["python","-m","calendar_service.server"]
