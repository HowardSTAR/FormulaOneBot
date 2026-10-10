// The installed job uses this trusted definition from /opt/f1hub-ci/Jenkinsfile.
// Only main is checked out; pull requests and other branches never deploy.
pipeline {
    agent any
    options {
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '10', removeLastBuild: true))
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        timeout(time: 90, unit: 'MINUTES')
        timestamps()
    }
    triggers {
        githubPush()
        // Scheduled runs build and test an isolated candidate; they never deploy.
        cron('TZ=Europe/Moscow\n0 9,21 * * *')
        // Recovery path if GitHub cannot deliver a webhook.
        pollSCM('H/5 * * * *')
    }
    environment {
        APP_IMAGE = "formulaonebot-ci:${BUILD_NUMBER}"
        CI_SCRIPTS = '/opt/f1hub-ci'
    }
    stages {
        stage('Checkout main') {
            steps {
                deleteDir()
                git branch: 'main', url: 'https://github.com/HowardSTAR/FormulaOneBot.git'
                sh 'mkdir -p reports .ci-data; git rev-parse HEAD > reports/commit.txt'
            }
        }
        stage('Build candidate') {
            steps { sh 'bash "$CI_SCRIPTS/run-ci.sh" build' }
        }
        stage('Frontend and game tests') {
            steps { sh 'bash "$CI_SCRIPTS/run-ci.sh" frontend' }
            post { always { junit allowEmptyResults: true, testResults: 'reports/frontend.xml,reports/game.xml' } }
        }
        stage('Python tests') {
            steps { sh 'bash "$CI_SCRIPTS/run-ci.sh" python' }
            post { always { junit allowEmptyResults: true, testResults: 'reports/pytest.xml' } }
        }
        stage('Isolated startup check') {
            steps { sh 'bash "$CI_SCRIPTS/run-ci.sh" smoke' }
        }
        stage('Deploy verified image') {
            when {
                allOf {
                    expression { currentBuild.currentResult == 'SUCCESS' }
                    // A timer cause takes precedence even if triggers are coalesced.
                    not { triggeredBy 'TimerTrigger' }
                    anyOf {
                        triggeredBy 'GitHubPushCause'
                        triggeredBy 'SCMTrigger'
                    }
                }
            }
            steps {
                sh '''
                    set -eu
                    current=$(git ls-remote origin refs/heads/main | cut -f1)
                    test -n "$current"
                    if [ "$current" = "$(git rev-parse HEAD)" ]; then
                        bash "$CI_SCRIPTS/run-ci.sh" deploy
                    else
                        printf '{"status":"superseded"}\\n' > reports/deployment.json
                        echo 'Newer main commit exists; this candidate will not deploy.'
                    fi
                '''
            }
        }
    }
    post {
        always {
            archiveArtifacts allowEmptyArchive: true, artifacts: 'reports/**/*'
            script {
                withCredentials([
                    string(credentialsId: 'ci-telegram-bot-token', variable: 'TELEGRAM_BOT_TOKEN'),
                    string(credentialsId: 'ci-telegram-admin-id', variable: 'TELEGRAM_CHAT_ID')
                ]) {
                    withEnv(["CI_RESULT=${currentBuild.currentResult}", "CI_DURATION=${currentBuild.durationString}"]) {
                        sh 'bash "$CI_SCRIPTS/run-ci.sh" notify'
                    }
                }
            }
        }
        cleanup {
            sh 'bash "$CI_SCRIPTS/run-ci.sh" cleanup'
            deleteDir()
        }
    }
}
