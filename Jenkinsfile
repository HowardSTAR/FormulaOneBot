pipeline {
    agent any

    options {
        ansiColor('xterm')
        buildDiscarder(logRotator(numToKeepStr: '30', artifactNumToKeepStr: '10'))
        disableConcurrentBuilds(abortPrevious: true)
        skipDefaultCheckout(true)
        timeout(time: 30, unit: 'MINUTES')
        timestamps()
    }

    environment {
        FRONTEND_IMAGE = 'node:20-alpine'
        PYTHON_IMAGE = 'python:3.11-slim'
        APP_IMAGE = "formulaonebot-ci:${BUILD_NUMBER}"
        // Jenkins credentials IDs; секреты в Git не хранятся.
        GITHUB_STATUS_CREDENTIALS = 'github-status-token'
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
                sh '''
                    set -eu
                    docker version
                    docker compose version
                    test -f front/package-lock.json
                    test -f requirements.txt
                    test -f app-assets.zip
                '''
            }
        }

        stage('Install Dependencies') {
            parallel {
                stage('Frontend dependencies') {
                    steps {
                        sh '''
                            docker run --rm \
                              -e npm_config_cache=/cache \
                              -v "$WORKSPACE/front:/workspace" \
                              -v f1hub_jenkins_npm_cache:/cache \
                              -w /workspace \
                              "$FRONTEND_IMAGE" \
                              npm ci --no-audit --no-fund
                        '''
                    }
                }
                stage('Python dependencies') {
                    steps {
                        sh '''
                            docker run --rm \
                              -v "$WORKSPACE:/workspace" \
                              -v f1hub_jenkins_pip_cache:/root/.cache/pip \
                              -w /workspace \
                              "$PYTHON_IMAGE" \
                              sh -ec 'pip install -r requirements.txt'
                        '''
                    }
                }
            }
        }

        stage('Quality & Tests') {
            parallel {
                stage('Frontend lint') {
                    steps {
                        sh '''
                            docker run --rm \
                              -v "$WORKSPACE/front:/workspace" \
                              -w /workspace \
                              "$FRONTEND_IMAGE" npm run lint
                        '''
                    }
                }
                stage('Python tests') {
                    steps {
                        sh '''
                            mkdir -p reports
                            docker run --rm \
                              -v "$WORKSPACE:/workspace" \
                              -v f1hub_jenkins_pip_cache:/root/.cache/pip \
                              -w /workspace \
                              "$PYTHON_IMAGE" \
                              sh -ec 'pip install -r requirements.txt && pytest --junitxml=reports/pytest.xml'
                        '''
                    }
                    post {
                        always {
                            junit allowEmptyResults: true, testResults: 'reports/pytest.xml'
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
                              -v "$WORKSPACE/front:/workspace" \
                              -w /workspace \
                              "$FRONTEND_IMAGE" npm run build
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

        stage('Integration smoke test') {
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
            script {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    githubNotify credentialsId: env.GITHUB_STATUS_CREDENTIALS,
                        description: 'Jenkins pipeline passed',
                        status: 'SUCCESS'
                }
            }
        }
        failure {
            script {
                catchError(buildResult: 'FAILURE', stageResult: 'UNSTABLE') {
                    githubNotify credentialsId: env.GITHUB_STATUS_CREDENTIALS,
                        description: 'Jenkins pipeline failed',
                        status: 'FAILURE'
                }
                // Опционально: создайте Secret text credentials `telegram-bot-token`
                // и `telegram-chat-id`, затем раскомментируйте этот блок.
                /*
                withCredentials([
                    string(credentialsId: 'telegram-bot-token', variable: 'TG_TOKEN'),
                    string(credentialsId: 'telegram-chat-id', variable: 'TG_CHAT_ID')
                ]) {
                    sh '''
                        curl --fail --silent --show-error \
                          --data-urlencode "chat_id=$TG_CHAT_ID" \
                          --data-urlencode "text=❌ Jenkins: ${JOB_NAME} #${BUILD_NUMBER} — ${BUILD_URL}" \
                          "https://api.telegram.org/bot${TG_TOKEN}/sendMessage"
                    '''
                }
                */
            }
        }
    }
}
