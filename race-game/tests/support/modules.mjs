import ts from 'typescript';
import {loadTs as compileModule} from '../../../scripts/testing/load-ts.mjs';
export const loadTs = (url, transform) => compileModule(url, ts, transform);
