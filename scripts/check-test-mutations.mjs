// Curated boundary mutants run in child processes against in-memory source copies.
// No application source files or real transports are changed.
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const cwd = fileURLToPath(new URL('../',import.meta.url));
const cases = [
  ['forecast-close', '/src/pages/index/personal-summary.ts', 'now < deadline', 'now <= deadline', 'front/tests/reminder-boundaries.test.mjs'],
  ['visit-close', '/src/helpers/visitReminders.ts', 'deadline>now', 'deadline>=now', 'front/tests/reminder-boundaries.test.mjs'],
  ['forecast-urgency', '/src/helpers/visitReminders.ts', 'deadline-now<=86400000', 'deadline-now<86400000', 'front/tests/reminder-boundaries.test.mjs'],
  ['session-end', '/src/helpers/reminderClock.ts', 'now < start + minutes * 60000', 'now <= start + minutes * 60000', 'front/tests/reminder-boundaries.test.mjs'],
  ['install-limit', '/src/helpers/installHint.ts', '(state.count ?? 0) < 3', '(state.count ?? 0) < 4', 'front/tests/installHint.test.mjs'],
  ['install-cooldown', '/src/helpers/installHint.ts', '>= 30 * 86400000', '> 30 * 86400000', 'front/tests/installHint.test.mjs'],
  ['finish-edge', '/src/finishLine.ts', 'y >= line.minY', 'y > line.minY', 'race-game/tests/boundaries.test.mjs'],
  ['physics-cap', '/src/raceClock.ts', 'Math.min(frameMs, 250)', 'Math.min(frameMs, 251)', 'race-game/tests/boundaries.test.mjs'],
];
function run(files,mutation) {
  const env = {...process.env};
  delete env.F1HUB_TEST_MUTATION;
  if (mutation) env.F1HUB_TEST_MUTATION=JSON.stringify(mutation);
  return spawnSync(process.execPath,['--test','--test-reporter=tap',...files],{cwd,env,encoding:'utf8',timeout:30000});
}
const baseline = run([...new Set(cases.map(row=>row[4]))]);
if (baseline.status!==0) {
  process.stderr.write(baseline.stdout+baseline.stderr);
  throw new Error('Unmodified tests must pass before evaluating mutants');
}
let killed=0;
for (const [name,path,from,to,file] of cases) {
  const result=run([file],{path,from,to});
  if (result.status!==0 && !result.error && /not ok/.test(result.stdout) && /AssertionError/.test(result.stdout)) {
    killed++; console.log(`Detected: ${name}`);
  } else {
    console.error(`Survived or invalid: ${name}\n${result.stdout}\n${result.stderr}`);
  }
}
console.log(`Boundary mutations detected: ${killed}/${cases.length}`);
if (killed!==cases.length) process.exitCode=1;
