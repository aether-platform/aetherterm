FROM ubuntu:16.04

RUN apt-get update \
 && apt-get install -y -q --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    python-dev \
    python-setuptools \
    ca-certificates \
 && easy_install pip \
 && pip install --upgrade setuptools \
 && apt-get clean \
 && rm -r /var/lib/apt/lists/*

WORKDIR /opt
ADD . /opt/app
WORKDIR /opt/app


ADD docker/run.sh /opt/run.sh

EXPOSE 57575

CMD ["src/aetherterm/server.py", "--unsecure", "--host=0.0.0.0"]
ENTRYPOINT ["docker/run.sh"]
