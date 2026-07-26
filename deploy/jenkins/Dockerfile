FROM docker:27-cli AS docker-cli

FROM jenkins/jenkins:lts-jdk17

USER root

# Jenkins управляет Docker хоста через /var/run/docker.sock. Берём только CLI:
# отдельный Docker daemon внутри контейнера не запускается.
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose \
    /usr/local/libexec/docker/cli-plugins/docker-compose

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl git openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && docker --version \
    && docker compose version

USER jenkins

# Плагины устанавливаются при сборке образа, а не вручную после каждого
# восстановления Jenkins. Зависимости разрешает официальный jenkins-plugin-cli.
COPY --chown=jenkins:jenkins plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt
