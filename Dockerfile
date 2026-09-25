# Start from the ASLscp pipeline image (kjobson/aslscp:0.2.5)
FROM kjobson/aslscp@sha256:REPLACE_WITH_DIGEST

ENV BASE_DIR=/flywheel/v0
WORKDIR ${BASE_DIR}

# Create non-root user
RUN useradd -m -s /bin/bash flywheel && chown -R flywheel:flywheel ${BASE_DIR}

# Install Python dependencies (fw-gear)
COPY pyproject.toml ${BASE_DIR}/
RUN pip3 install --no-cache-dir .

COPY run.py manifest.json ${BASE_DIR}/

USER flywheel
ENTRYPOINT ["python3", "/flywheel/v0/run.py"]
