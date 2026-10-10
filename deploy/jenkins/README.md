# Jenkins CI и автоматическое развёртывание F1Hub

Панель: https://jenkins.f1hub.ru/ . Задание: F1Hub-main.

Конфигурация рассчитана на существующий сервер Ubuntu/Docker: production
Compose-проект formulaonebot в /root/FormulaOneBot. Nginx уже занимает 80/443.

## Запуски и проверки

- Только main из HowardSTAR/FormulaOneBot; другие ветки не развёртываются.
- Подписанный GitHub webhook после push; резервный Poll SCM каждые 5 минут.
- Ежедневно в 09:00 и 21:00, Europe/Moscow: сборка и все проверки
  в изолированных контейнерах, без развёртывания и перезапуска приложения.
- После push в main (webhook или резервный Poll SCM): сборка, все проверки,
  затем развёртывание проверенного образа. Poll SCM запускает сборку только
  при изменениях. Ручной запуск выполняет только сборку и проверки.
- Один executor, очередь сборок, последние 10 прогонов и отчётов.
- Checkout → Docker build → lint и frontend/game tests → pytest →
  изолированный health check. Только для запуска после push далее выполняются
  развёртывание и публичный health check.
- Развёртывается тот же образ, который прошёл проверки. Ошибка любой проверки
  пропускает обновление приложения. Устаревший commit не развёртывается.
- Если один прогон объединяет таймер и push, таймер имеет приоритет:
  развёртывание пропускается. Неизвестные причины запуска также не развёртывают образ.
- После каждого прогона результат, число тестов и ссылка приходят в Telegram.
- Сгенерированный bundle front/public/race-game исключён из lint;
  исходники игры проверяются TypeScript-сборкой и тестами.
- Тесты используют отдельную БД и фиктивный Telegram token.
- Серверный набор запускается с `--live`: включены проверки настоящих FastF1
  и OpenF1. Они только читают API и не меняют результаты или рассылки.

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

Неизменившийся образ не вызывает перезапуска приложения. После каждого прогона
удаляются временные кандидаты и старые образы приложения: `formulaonebot-ci`,
`formulaonebot-app`, `formulaonebot-rollback`, `formulaonebot-bot`, `formulaonebot-web`.
Новые образы получают label `ru.f1hub.ci.app=true`, позволяющий удалять их и после
потери тегов. Сохраняются текущий образ, `formulaonebot-rollback:previous` и образы,
используемые любыми контейнерами (включая остановленные). Удаление без `--force`.
Старые образы без тегов и без label нельзя уверенно отнести к приложению,
поэтому они автоматически не удаляются. CI cache ограничен.
Volumes Redis и рабочие данные не очищаются.

## Обслуживание

Доверенная установленная конфигурация CI: /opt/f1hub-ci.
Workspace: /srv/jenkins-workspace — один и тот же путь на хосте и в Jenkins.
Jenkins home: volume f1hub_jenkins_home.
Job использует установленную копию Jenkinsfile: checkout приложения сам по себе
не заменяет конфигурацию CI. Изменения CI-файлов требуют установки администратором.

Для применения этих изменений на сервере дождитесь окончания текущей сборки,
сохраните копию `/opt/f1hub-ci`, затем установите новый `Jenkinsfile` в
`/opt/f1hub-ci/Jenkinsfile`, а `deploy/jenkins/run-ci.sh` и
`deploy/jenkins/cleanup-images.sh` — в одноимённые файлы `/opt/f1hub-ci`.
Скрипты должны быть доступны Jenkins для чтения.
В административной [Script Console](https://jenkins.f1hub.ru/script) выполните
содержимое `deploy/jenkins/update-job.groovy`: оно обновляет определение job и
сразу устанавливает таймер на 09:00/21:00 по Москве, сохраняя webhook и Poll SCM. Bootstrap повторять
не нужно; сборка и перезапуск приложения при обновлении job не запускаются.
Для разовой очистки накопленных образов на Docker-хосте выполните
`bash /opt/f1hub-ci/cleanup-images.sh`; далее очистка работает в конце прогонов.

Jenkins: LTS/Java 21, лимит 1 CPU/1 ГБ, Java heap 512 МБ.
Тесты также имеют ограничения ресурсов. BuildKit: 1 CPU/1 ГБ RAM,
до 512 МБ swap, один шаг сборки одновременно. На сервере создан
/swapfile-ci на 512 МБ с автоматическим подключением после перезагрузки.
Node heap при Docker-сборке ограничен 512 МБ. Метаданные версии добавляются
после установки зависимостей, чтобы новый commit не заставлял устанавливать их заново.
Кэш CI ограничен 1500 МБ, кэш стандартного builder — 512 МБ;
в настройках BuildKit размеры заданы строками с единицами измерения.

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
