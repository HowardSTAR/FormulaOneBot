// Run in the Jenkins administrator Script Console after installing CI files.
// Updates the trusted Pipeline without bootstrap, password reset or a build.
import jenkins.model.Jenkins
import org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition
import hudson.triggers.TimerTrigger

def job = Jenkins.get().getItem('F1Hub-main')
assert job != null : 'F1Hub-main job is missing'
assert !job.isBuilding() : 'Wait until the current build finishes before updating CI'
job.setDefinition(new CpsFlowDefinition(new File('/opt/f1hub-ci/Jenkinsfile').text, true))
job.addTrigger(new TimerTrigger('TZ=Europe/Moscow\n0 9,21 * * *'))
job.setDescription('Trusted main only. 09:00 and 21:00 Europe/Moscow: build and tests only. GitHub push + SCM polling: tests and verified deployment. Telegram results.')
job.save()
println('F1Hub-main updated. 09:00/21:00 builds test only; push builds may deploy. No build started.')
