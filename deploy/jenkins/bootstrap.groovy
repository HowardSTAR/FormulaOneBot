import jenkins.model.Jenkins
import jenkins.model.JenkinsLocationConfiguration
import hudson.model.User
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.GlobalMatrixAuthorizationStrategy
import hudson.util.Secret
import hudson.tasks.LogRotator
import com.cloudbees.plugins.credentials.SystemCredentialsProvider
import com.cloudbees.plugins.credentials.CredentialsScope
import com.cloudbees.plugins.credentials.domains.Domain
import org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl
import org.jenkinsci.plugins.github.config.GitHubPluginConfig
import org.jenkinsci.plugins.github.config.HookSecretConfig
import org.jenkinsci.plugins.workflow.job.WorkflowJob
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition
import groovy.json.JsonSlurper
import groovy.json.JsonOutput
import jenkins.security.ApiTokenProperty

def j = Jenkins.get()
def source = new File('/run/f1hub-ci-bootstrap/secrets.json')
if (!source.exists()) { return }
def values = new JsonSlurper().parse(source)
def realm = new HudsonPrivateSecurityRealm(false)
realm.createAccount(values.username, values.password)
j.setSecurityRealm(realm)
def auth = new GlobalMatrixAuthorizationStrategy()
auth.add(Jenkins.ADMINISTER, values.username)
j.setAuthorizationStrategy(auth)
j.setNumExecutors(1)
j.setLabelString('trusted-main')
def location = JenkinsLocationConfiguration.get()
location.setUrl('https://jenkins.f1hub.ru/')
location.save()
def store = SystemCredentialsProvider.getInstance().getStore()
[
    'ci-telegram-bot-token': values.bot_token,
    'ci-telegram-admin-id': values.chat_id,
    'ci-webhook-secret': values.webhook_secret
].each { id, value ->
    def old = store.getCredentials(Domain.global()).find { it.id == id }
    def cred = new StringCredentialsImpl(CredentialsScope.GLOBAL, id, 'F1Hub CI', Secret.fromString(value.toString()))
    if (old) { store.updateCredentials(Domain.global(), old, cred) }
    else { store.addCredentials(Domain.global(), cred) }
}
def github = jenkins.model.GlobalConfiguration.all().get(GitHubPluginConfig.class)
github.setHookSecretConfigs([new HookSecretConfig('ci-webhook-secret')])
github.save()
def job = j.getItem('F1Hub-main') ?: j.createProject(WorkflowJob.class, 'F1Hub-main')
job.setDefinition(new CpsFlowDefinition(new File('/opt/f1hub-ci/Jenkinsfile').text, true))
job.setDescription('Trusted main only. 09:00 and 21:00 Europe/Moscow: build and tests only. GitHub push + SCM polling: tests and verified deployment. Telegram results.')
def retention = new LogRotator(-1, 10, -1, 10)
retention.setRemoveLastBuild(true)
job.setBuildDiscarder(retention)
job.setConcurrentBuild(false)
job.setQuietPeriod(5)
job.save()
def user = User.getById(values.username, true)
def token = user.getProperty(ApiTokenProperty.class).tokenStore.generateNewToken('temporary-ci-setup')
user.save()
def api = new File(j.rootDir, 'ci-bootstrap-api.json')
api.text = JsonOutput.toJson([username:values.username, token:token.plainValue, uuid:token.tokenUuid])
api.setReadable(false, false)
api.setReadable(true, true)
api.setWritable(false, false)
api.setWritable(true, true)
j.save()
println('F1Hub CI bootstrap complete; secrets are not logged.')
