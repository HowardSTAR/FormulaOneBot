# Jenkins CI и автоматическое развёртывание F1Hub

Панель: https://jenkins.f1hub.ru/ . Задание: F1Hub-main.

Конфигурация рассчитана на существующий сервер Ubuntu/Docker: production
Compose-проект formulaonebot в /root/FormulaOneBot. Nginx уже занимает 80/443.

## Запуски и проверки

- Только main из HowardSTAR/FormulaOneBot; другие ветки не развёртываются.
- Подписанный GitHub webhook после push; резервный Poll SCM каждые 5 минут.
- Ежедневно в 09:00 и 21:00, Europe/Moscow.
- Один executor, очередь сборок, последние 10 прогонов и отчётов.
- Checkout → Docker build → lint и frontend/game tests → pytest →
  изолированный health check → развёртывание → публичный health check.
- Развёртывается тот же образ, который прошёл проверки. Ошибка любой проверки
  пропускает обновление приложения. Устаревший commit не развёртывается.
- После каждого прогона результат, число тестов и ссылка приходят в Telegram.
- Сгенерированный bundle front/public/race-game исключён из lint;
  исходники игры проверяются TypeScript-сборкой и тестами.
- Тесты используют отдельную БД и фиктивный Telegram token.

## Доступ

Только f1hub-admin имеет права. Регистрация и анонимное чтение отключены.
Порт 8080 доступен только на loopback, публичная панель работает по HTTPS.
Webhook защищён подписью SHA-256.

Пароль: /root/f1hub-ci/login.txt, права 600. С разрешения пользователя создана
локальная копия secrets/jenkins-login.txt, исключённая из Git.
Telegram token и ID находятся в Jenkins Credentials ci-telegram-bot-token,
ci-telegram-admin-id; webhook secret — ci-webhook-secret.

## Развёртывание и откат

Перед обновлением deploy-verified.sh создаёт online backup SQLite:
/root/FormulaOneBot/data/ci-backups/before-last-deploy.db.
Предыдущий образ сохраняется как formulaonebot-rollback:previous.
Проверенный образ получает тег formulaonebot-app:latest; bot/web пересоздаются
с --no-build --no-deps --wait, затем Nginx перечитывает адрес web.

Ошибка запуска или публичного health check возвращает предыдущий образ.
Неудачный откат отмечается отдельным сообщением администратору.
База автоматически не откатывается, чтобы не потерять новые записи.
Будущие изменения схемы должны сохранять совместимость с предыдущей версией.

Неизменившийся образ не вызывает перезапуска приложения. Временные кандидаты
удаляются; остаются текущий и предыдущий образы. CI cache ограничен.
Volumes Redis и рабочие данные не очищаются.

## Обслуживание

Доверенная установленная конфигурация CI: /opt/f1hub-ci.
Workspace: /srv/jenkins-workspace — один и тот же путь на хосте и в Jenkins.
Jenkins home: volume f1hub_jenkins_home.
Job использует установленную копию Jenkinsfile: checkout приложения сам по себе
не заменяет конфигурацию CI. Изменения CI-файлов требуют установки администратором.

Jenkins: LTS/Java 21, лимит 1 CPU/1 ГБ, Java heap 512 МБ.
Тесты и BuildKit также имеют ограничения ресурсов.

```bash
docker compose --project-directory /opt/f1hub-ci -f /opt/f1hub-ci/docker-compose.yml ps
docker logs --tail=100 f1hub-jenkins
python3 /opt/f1hub-ci/test_deploy.py
certbot renew --dry-run
```

TLS обслуживает существующий Nginx-контейнер. Certbot использует webroot
/root/FormulaOneBot/ssl/acme. Renewal deploy hook копирует сертификаты в ssl
и проверяет/перечитывает Nginx.

Первичная установка: configure-server.py, bootstrap.groovy, configure-tls.py.
Backup перед изменениями: /root/f1hub-ci-backups. Bootstrap-секреты и временный
setup API token удаляются после проверки. Повторный bootstrap создаёт новый
пароль, поэтому не используйте его при обычном обновлении.

## Документация

- [Jenkins Pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/)
- [Reverse proxy](https://www.jenkins.io/doc/book/system-administration/reverse-proxy-configuration-with-jenkins/)
- [BuildKit limits](https://docs.docker.com/build/builders/drivers/docker-container/)
