# Start from the ASLscp pipeline image (kjobson/aslscp:0.3.3)
FROM --platform=linux/amd64 kjobson/aslscp:0.3.3

ENV BASE_DIR=/flywheel/v0
WORKDIR ${BASE_DIR}

# Create non-root user
RUN useradd -m -s /bin/bash flywheel && chown -R flywheel:flywheel ${BASE_DIR}

# Install Python dependencies (fw-gear)
COPY pyproject.toml ${BASE_DIR}/
RUN /usr/bin/python3 -m pip install --no-cache-dir --upgrade pip==25.0.1 && \
    /usr/bin/python3 -m pip install --no-cache-dir .

COPY run.py manifest.json ${BASE_DIR}/

# Pipeline's `python3` -> system Python (run.py puts this first on PATH)
RUN mkdir -p /opt/gear-bin && ln -s /usr/bin/python3 /opt/gear-bin/python3

USER flywheel
ENTRYPOINT ["/usr/bin/python3", "/flywheel/v0/run.py"]
