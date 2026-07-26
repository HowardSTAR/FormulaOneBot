ARG JENKINS_IMAGE=jenkins/jenkins:lts-jdk17

FROM docker:27-cli AS docker-cli
FROM ${JENKINS_IMAGE}

USER root

# В контроллер добавляется только Docker CLI. Docker daemon работает на Ubuntu-хосте.
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose \
    /usr/local/libexec/docker/cli-plugins/docker-compose

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
       ca-certificates curl git openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && docker --version \
    && docker compose version

USER jenkins

# Базовый набор ставится воспроизводимо при сборке образа.
COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
