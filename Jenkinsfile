pipeline {
    agent any

    triggers {
        // Для обычного GitHub Pipeline. В Multibranch Pipeline события также
        // обрабатывает GitHub Branch Source.
        githubPush()
    }

    options {
        ansiColor('xterm')
        buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '10'))
        disableConcurrentBuilds(abortPrevious: true)
        skipDefaultCheckout(true)
        timeout(time: 40, unit: 'MINUTES')
        timestamps()
    }

    environment {
        FRONTEND_IMAGE = 'node:20-alpine'
        PYTHON_IMAGE = 'formulaonebot-python-ci:3.11'
        CURL_IMAGE = 'curlimages/curl:8.12.1'
        APP_IMAGE = "formulaonebot-ci:${BUILD_NUMBER}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --pretty="format:Building %h — %s"'
            }
        }

        stage('Environment Setup') {
            steps {
                script {
                    env.HOST_WORKSPACE = sh(
                        returnStdout: true,
                        script: '''
                            set -eu
                            : "${JENKINS_HOME_HOST:?JENKINS_HOME_HOST is not set by Docker Compose}"
                            case "$WORKSPACE" in
                              /var/jenkins_home/*)
                                printf '%s%s' "$JENKINS_HOME_HOST" "${WORKSPACE#/var/jenkins_home}"
                                ;;
                              *)
                                echo "Unsupported WORKSPACE path: $WORKSPACE" >&2
                                exit 1
                                ;;
                            esac
                        '''
                    ).trim()
                }

                sh '''
                    set -eu
                    docker version
                    docker compose version
                    test -f front/package-lock.json
                    test -f requirements.txt
                    test -f requirements-ci.txt
                    test -f app-assets.zip
                    rm -rf reports front/dist .ci/test.db
                    mkdir -p \
                      .ci/cache/npm \
                      .ci/cache/pip \
                      .ci/home/node \
                      .ci/home/python \
                      reports

                    docker build --pull \
                      --file deploy/jenkins/python-ci.Dockerfile \
                      --tag "$PYTHON_IMAGE" \
                      deploy/jenkins

                    # Тесты ассетов ожидают app/assets; production Dockerfile
                    # распаковывает тот же архив во время сборки образа.
                    docker run --rm \
                      --user "$(id -u):$(id -g)" \
                      -e HOME=/workspace/.ci/home/python \
                      -v "$HOST_WORKSPACE:/workspace" \
                      -w /workspace \
                      "$PYTHON_IMAGE" \
                      sh -ec 'rm -rf app/assets && python -m zipfile -e app-assets.zip .'
                '''
            }
        }

        stage('Install Dependencies') {
            parallel {
                stage('Frontend dependencies') {
                    steps {
                        sh '''
                            docker run --rm \
                              --user "$(id -u):$(id -g)" \
                              -e HOME=/workspace/.ci/home/node \
                              -e npm_config_cache=/workspace/.ci/cache/npm \
                              -v "$HOST_WORKSPACE:/workspace" \
                              -w /workspace/front \
                              "$FRONTEND_IMAGE" \
                              npm ci --no-audit --no-fund
                        '''
                    }
                }

                stage('Python dependencies') {
                    steps {
                        sh '''
                            docker run --rm \
                              --user "$(id -u):$(id -g)" \
                              -e HOME=/workspace/.ci/home/python \
                              -e PIP_CACHE_DIR=/workspace/.ci/cache/pip \
                              -v "$HOST_WORKSPACE:/workspace" \
                              -w /workspace \
                              "$PYTHON_IMAGE" \
                              sh -ec '
                                test -x .ci/venv/bin/python || python -m venv .ci/venv
                                .ci/venv/bin/python -m pip install --upgrade pip
                                .ci/venv/bin/python -m pip install -r requirements-ci.txt
                              '
                        '''
                    }
                }
            }
        }

        stage('Quality & Tests') {
            parallel {
                stage('Frontend lint & types') {
                    steps {
                        sh '''
                            docker run --rm \
                              --user "$(id -u):$(id -g)" \
                              -e HOME=/workspace/.ci/home/node \
                              -e npm_config_cache=/workspace/.ci/cache/npm \
                              -v "$HOST_WORKSPACE:/workspace" \
                              -w /workspace/front \
                              "$FRONTEND_IMAGE" \
                              sh -ec 'npm run lint && npx tsc -b --pretty false'
                        '''
                    }
                }

                stage('Python tests') {
                    steps {
                        sh '''
                            docker run --rm \
                              --user "$(id -u):$(id -g)" \
                              -e HOME=/workspace/.ci/home/python \
                              -e PYTHONPATH=/workspace \
                              -e DATABASE_PATH=/workspace/.ci/test.db \
                              -v "$HOST_WORKSPACE:/workspace" \
                              -w /workspace \
                              "$PYTHON_IMAGE" \
                              .ci/venv/bin/python -m pytest \
                                --junitxml=reports/pytest.xml \
                                --html=reports/pytest.html \
                                --self-contained-html
                        '''
                    }
                    post {
                        always {
                            junit(
                                allowEmptyResults: true,
                                keepLongStdio: true,
                                testResults: 'reports/pytest.xml'
                            )
                            publishHTML(target: [
                                allowMissing: true,
                                alwaysLinkToLastBuild: true,
                                keepAll: true,
                                reportDir: 'reports',
                                reportFiles: 'pytest.html',
                                reportName: 'Pytest HTML Report'
                            ])
                        }
                    }
                }
            }
        }

        stage('Build') {
            parallel {
                stage('Frontend build') {
                    steps {
                        sh '''
                            docker run --rm \
                              --user "$(id -u):$(id -g)" \
                              -e HOME=/workspace/.ci/home/node \
                              -e npm_config_cache=/workspace/.ci/cache/npm \
                              -v "$HOST_WORKSPACE:/workspace" \
                              -w /workspace/front \
                              "$FRONTEND_IMAGE" \
                              npm run build
                        '''
                    }
                }

                stage('Application image') {
                    steps {
                        sh 'docker build --pull --tag "$APP_IMAGE" .'
                    }
                }
            }
        }

        stage('Integration Smoke Test') {
            steps {
                sh '''
                    set -eu
                    container_id="$(
                      docker run -d \
                        -e BOT_TOKEN=123456:CI_PLACEHOLDER_TOKEN \
                        -e AUTH_PEPPER=ci-only-pepper-with-enough-entropy \
                        -e DATABASE_PATH=/tmp/formulaonebot-ci.db \
                        -p 127.0.0.1::8000 \
                        "$APP_IMAGE"
                    )"
                    trap 'docker rm -f "$container_id" >/dev/null 2>&1 || true' EXIT
                    port="$(docker port "$container_id" 8000/tcp | sed 's/.*://')"

                    attempt=0
                    until docker run --rm --network host "$CURL_IMAGE" \
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
            archiveArtifacts(
                allowEmptyArchive: true,
                artifacts: 'reports/**/*,front/dist/**/*',
                fingerprint: true
            )
            sh 'docker image rm "$APP_IMAGE" >/dev/null 2>&1 || true'
        }
        success {
            echo "SUCCESS: ${JOB_NAME} #${BUILD_NUMBER} — ${BUILD_URL}"
        }
        unstable {
            echo "UNSTABLE: ${JOB_NAME} #${BUILD_NUMBER} — проверьте отчёты."
        }
        failure {
            echo "FAILURE: ${JOB_NAME} #${BUILD_NUMBER} — ${BUILD_URL}"
        }
    }
}
