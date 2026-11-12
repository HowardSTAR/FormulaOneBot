import groovy.json.JsonSlurper
import hudson.security.HudsonPrivateSecurityRealm
import hudson.security.FullControlOnceLoggedInAuthorizationStrategy
import jenkins.model.Jenkins
import jenkins.model.JenkinsLocationConfiguration
import jenkins.install.InstallState

def j = Jenkins.get()
def marker = new File(j.rootDir, '.f1hub-vps-initialized')
if (marker.exists()) { return }
def source = new File('/run/f1hub-ci-bootstrap/secrets.json')
if (!source.exists()) { throw new IllegalStateException('Private Jenkins bootstrap credentials are missing') }
def values = new JsonSlurper().parse(source)
def realm = new HudsonPrivateSecurityRealm(false)
realm.createAccount(values.username.toString(), values.password.toString())
j.setSecurityRealm(realm)
def auth = new FullControlOnceLoggedInAuthorizationStrategy()
auth.setAllowAnonymousRead(false)
j.setAuthorizationStrategy(auth)
j.setNumExecutors(1)
j.setSlaveAgentPort(-1)
j.setLabelString('f1hub-vps')
def location = JenkinsLocationConfiguration.get()
location.setUrl('https://jenkins.f1hub.ru/')
location.save()
j.setInstallState(InstallState.INITIAL_SETUP_COMPLETED)
j.save()
marker.text = 'Fresh VPS instance; anonymous access and registration disabled.\n'
println('F1Hub Jenkins initialized securely; no builds or deployment jobs have been scheduled.')
