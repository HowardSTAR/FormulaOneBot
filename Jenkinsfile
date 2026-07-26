pipeline {
    agent any

    options {
        ansiColor('xterm')
        buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '10'))
        disableConcurrentBuilds(abortPrevious: true)
        skipDefaultCheckout(true)
        timeout(time: 60, unit: 'MINUTES')
        timestamps()
    }

    triggers {
        // Соответствует опции "GitHub hook trigger for GITScm polling".
        githubPush()
    }

    environment {
        FRONTEND_IMAGE = 'node:20-alpine'
        APP_IMAGE = "formulaonebot-ci:${BUILD_NUMBER}"
        // Jenkins Credentials ID. Секрет хранится только в Jenkins, не в Git.
        GITHUB_STATUS_CREDENTIALS = 'github-status-token'
    }

    stages {
        stage('Checkout') {
            steps {
                // Удаляем файлы предыдущего запуска, включая распакованные ассеты.
                deleteDir()
                checkout scm
                sh 'git log -1 --pretty="format:Building %h — %s"'
            }
        }

        stage('Environment Setup') {
            steps {
                sh '''
                    set -eu
                    docker version
                    docker compose version
                    test -f front/package-lock.json
                    test -f requirements.txt
                    test -f app-assets.zip
                    test -f Dockerfile
                    mkdir -p reports .ci-data
                '''
            }
        }

        stage('Frontend Dependencies') {
            steps {
                // UID/GID Jenkins предотвращают появление root-owned файлов в workspace.
                sh '''
                    docker run --rm \
                      --user "$(id -u):$(id -g)" \
                      -e HOME=/tmp \
                      -e npm_config_cache=/tmp/npm-cache \
                      -v "$WORKSPACE/front:/workspace" \
                      -w /workspace \
                      "$FRONTEND_IMAGE" \
                      npm ci --no-audit --no-fund
                '''
            }
        }

        stage('Frontend Quality') {
            parallel {
                stage('Lint') {
                    steps {
                        sh '''
                            docker run --rm \
                              --user "$(id -u):$(id -g)" \
                              -e HOME=/tmp \
                              -v "$WORKSPACE/front:/workspace" \
                              -w /workspace \
                              "$FRONTEND_IMAGE" npm run lint
                        '''
                    }
                }
                stage('Production Build') {
                    steps {
                        sh '''
                            docker run --rm \
                              --user "$(id -u):$(id -g)" \
                              -e HOME=/tmp \
                              -v "$WORKSPACE/front:/workspace" \
                              -w /workspace \
                              "$FRONTEND_IMAGE" npm run build
                        '''
                    }
                }
            }
        }

        stage('Build Application Image') {
            steps {
                // Dockerfile распаковывает app-assets.zip. Тесты ниже запускаются
                // в точном production-образе и видят полный комплект ассетов.
                sh 'docker build --pull --tag "$APP_IMAGE" .'
            }
        }

        stage('Python Tests') {
            steps {
                sh '''
                    docker run --rm \
                      --user "$(id -u):$(id -g)" \
                      -e HOME=/tmp \
                      -e BOT_TOKEN=123456:TEST \
                      -e ADMIN_EMAIL=ci-admin@example.invalid \
                      -e ADMIN_TELEGRAM_ID=100000001 \
                      -e DATABASE_PATH=/app/data/ci.db \
                      -v "$WORKSPACE/tests:/app/tests:ro" \
                      -v "$WORKSPACE/pytest.ini:/app/pytest.ini:ro" \
                      -v "$WORKSPACE/reports:/app/reports" \
                      -v "$WORKSPACE/.ci-data:/app/data" \
                      -w /app \
                      "$APP_IMAGE" \
                      pytest --junitxml=/app/reports/pytest.xml
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'reports/pytest.xml'
                }
            }
        }

        stage('Integration Smoke Test') {
            steps {
                sh '''
                    set -eu
                    container_id="$(docker run -d -p 127.0.0.1::8000 "$APP_IMAGE")"
                    trap 'docker rm -f "$container_id" >/dev/null 2>&1 || true' EXIT
                    port="$(docker port "$container_id" 8000/tcp | sed 's/.*://')"
                    attempt=0
                    until docker run --rm --network host curlimages/curl:8.12.1 \
                      --fail --silent "http://127.0.0.1:${port}/health" >/dev/null; do
                        attempt=$((attempt + 1))
                        if [ "$attempt" -ge 30 ]; then
                            docker logs "$container_id"
                            exit 1
                        fi
                        sleep 2
                    done
                '''
            }
        }
    }

    post {
        always {
            archiveArtifacts allowEmptyArchive: true,
                artifacts: 'reports/**/*,front/dist/**/*',
                fingerprint: true
            sh 'docker image rm "$APP_IMAGE" >/dev/null 2>&1 || true'
        }
        success {
            echo 'Все проверки прошли успешно.'
            script {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    githubNotify credentialsId: env.GITHUB_STATUS_CREDENTIALS,
                        description: 'Jenkins pipeline passed',
                        status: 'SUCCESS'
                }
            }
        }
        failure {
            echo 'Одна или несколько проверок завершились ошибкой.'
            script {
                catchError(buildResult: 'FAILURE', stageResult: 'UNSTABLE') {
                    githubNotify credentialsId: env.GITHUB_STATUS_CREDENTIALS,
                        description: 'Jenkins pipeline failed',
                        status: 'FAILURE'
                }
            }
        }
        cleanup {
            deleteDir()
        }
    }
}
