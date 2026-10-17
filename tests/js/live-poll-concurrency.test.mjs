import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

const source = readFileSync(new URL('../../app/tesla/static/js/view/live-driving.js', import.meta.url), 'utf8');
const pollSource = source.match(/async function poll\(\) \{[\s\S]*?\n\}/)[0];

test('slow status polling stays single-flight and retries after failure', async () => {
  let calls = 0;
  let fail;
  const context = vm.createContext({
    lvGen: 1, shellState: {carId: null},
    getJSON() {
      calls++;
      return new Promise((_, reject) => { fail = reject; });
    },
  });
  vm.runInContext('let lvPollPending = false;\n' + pollSource, context);
  const first = context.poll();
  const duplicate = context.poll();
  assert.equal(calls, 1);
  fail(new Error('network timeout'));
  await Promise.all([first, duplicate]);
  const retry = context.poll();
  assert.equal(calls, 2);
  fail(new Error('network timeout'));
  await retry;
});
