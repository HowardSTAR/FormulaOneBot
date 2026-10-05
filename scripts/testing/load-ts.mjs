import {readFileSync} from 'node:fs';

/** Use the package's compiler while keeping transformations and mutation checks shared. */
export async function loadTs(url, ts, transform = source => source) {
  let source = readFileSync(url, 'utf8');
  const mutation = process.env.F1HUB_TEST_MUTATION && JSON.parse(process.env.F1HUB_TEST_MUTATION);
  if (mutation && url.pathname.endsWith(mutation.path)) {
    if (source.split(mutation.from).length !== 2) throw new Error('Mutation must match exactly once');
    source = source.replace(mutation.from, mutation.to);
  }
  const {outputText} = ts.transpileModule(transform(source), {compilerOptions: {
    module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React,
  }});
  return import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
}
