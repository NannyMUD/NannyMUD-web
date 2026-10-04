FROM python:3.12-slim
RUN pip install --no-cache-dir jinja2==3.1.4 markdown==3.7 beautifulsoup4==4.12.3 \
 && apt-get update && apt-get install -y --no-install-recommends curl tzdata \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /site
COPY build.py stats.py ./
COPY templates templates
COPY static static
COPY content content
COPY times times
COPY scripts scripts
COPY docker/builder.sh /builder.sh
CMD ["sh", "/builder.sh"]
