// Quipu API flow tests (Postman/Newman) — Jenkins pipeline
// Runs the SMOKE health suite (and optionally the auth flow) against a chosen environment,
// publishes JUnit + HTML reports. Onprem uses self-signed TLS -> newman runs with --insecure.

pipeline {
  // Uses a Node container so the agent needs only Docker. Swap for `agent { label 'linux' }`
  // if your agents already have Node 18+ installed.
  agent {
    docker {
      image 'node:20-bullseye'
      args  '-u root:root'
    }
  }

  parameters {
    choice(name: 'ENVIRONMENT', choices: ['onprem', 'local', 'stage', 'pre-prod', 'prod'],
           description: 'Target environment (selects environments/<env>.postman_environment.json)')
    choice(name: 'SUITE', choices: ['smoke', 'auth', 'all'],
           description: 'smoke = platform health; auth = Keycloak token flow; all = both')
    booleanParam(name: 'FAIL_ON_TEST_FAILURE', defaultValue: true,
           description: 'Fail the build if any assertion fails (health gate). Uncheck to report-only.')
  }

  options {
    timestamps()
    ansiColor('xterm')
    disableConcurrentBuilds()
    buildDiscarder(logRotator(numToKeepStr: '30'))
    timeout(time: 20, unit: 'MINUTES')
  }

  environment {
    // onprem & local use self-signed certs; hosted envs presumably have valid certs.
    INSECURE = "${(params.ENVIRONMENT in ['onprem', 'local']) ? '--insecure' : ''}"
    ENVFILE  = "environments/${params.ENVIRONMENT}.postman_environment.json"
  }

  stages {
    stage('Checkout') {
      steps { checkout scm }
    }

    stage('Setup Newman') {
      steps {
        sh '''
          set -e
          node --version && npm --version
          npm install -g newman newman-reporter-htmlextra
          newman --version
          mkdir -p reports
        '''
      }
    }

    stage('SMOKE – Platform Health') {
      when { expression { params.SUITE in ['smoke', 'all'] } }
      steps {
        sh '''
          set -e
          EXTRA=""
          [ "${FAIL_ON_TEST_FAILURE}" = "false" ] && EXTRA="--suppress-exit-code"
          newman run "flows/SMOKE-Platform-Health.postman_collection.json" \
            -e "${ENVFILE}" ${INSECURE} ${EXTRA} \
            -r cli,htmlextra,junit \
            --reporter-junit-export   "reports/smoke-${ENVIRONMENT}.xml" \
            --reporter-htmlextra-export "reports/smoke-${ENVIRONMENT}.html" \
            --timeout-request 30000
        '''
      }
    }

    stage('FLOW – Auth (Keycloak)') {
      when { expression { params.SUITE in ['auth', 'all'] } }
      steps {
        // Secrets from Vault (Vault plugin). Adjust the path/keys to your Vault layout.
        // Alternative without the Vault plugin: use withCredentials([string(...)]).
        withVault(configuration: [vaultUrl: env.VAULT_ADDR ?: 'https://vault.thequipu.in', vaultCredentialId: 'vault-approle'],
                  vaultSecrets: [[path: "secret/quipu/${params.ENVIRONMENT}", secretValues: [
                    [envVar: 'KC_CLIENT_SECRET', vaultKey: 'client_secret'],
                    [envVar: 'TEST_USERNAME',    vaultKey: 'test_username'],
                    [envVar: 'TEST_PASSWORD',    vaultKey: 'test_password']
                  ]]]) {
          sh '''
            set -e
            EXTRA=""
            [ "${FAIL_ON_TEST_FAILURE}" = "false" ] && EXTRA="--suppress-exit-code"
            newman run "flows/FLOW-Auth-Token.postman_collection.json" \
              -e "${ENVFILE}" ${INSECURE} ${EXTRA} \
              --env-var "client_secret=${KC_CLIENT_SECRET}" \
              --env-var "test_username=${TEST_USERNAME}" \
              --env-var "test_password=${TEST_PASSWORD}" \
              -r cli,junit \
              --reporter-junit-export "reports/auth-${ENVIRONMENT}.xml" \
              --timeout-request 30000
          '''
        }
      }
    }
  }

  post {
    always {
      junit testResults: 'reports/*.xml', allowEmptyResults: true
      archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true, fingerprint: true
      publishHTML(target: [
        reportName: "Newman ${params.ENVIRONMENT}",
        reportDir: 'reports', reportFiles: "smoke-${params.ENVIRONMENT}.html",
        keepAll: true, alwaysLinkToLastBuild: true, allowMissing: true
      ])
    }
    failure {
      echo "Health/flow check FAILED for ${params.ENVIRONMENT}. See the Newman HTML report."
    }
  }
}
