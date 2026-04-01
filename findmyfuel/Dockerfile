ARG BUILD_FROM
FROM $BUILD_FROM

WORKDIR /app

RUN apk add --no-cache python3 py3-pip

COPY app/pyproject.toml /app/pyproject.toml
COPY app/README.md /app/README.md
COPY app/src /app/src
RUN pip3 install --no-cache-dir /app

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
