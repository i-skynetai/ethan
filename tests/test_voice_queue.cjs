const assert = require('node:assert/strict');
const queue = require('../ethan/web/voice_queue.js');
(async () => {
  const calls = []; let release;
  const run = queue(async action => { calls.push(action); if(action === 'start') await new Promise(resolve => { release = resolve; }); });
  const start = run('start'); const stop = run('stop'); const cancel = run('cancel');
  await Promise.resolve(); await Promise.resolve();
  assert.deepEqual(calls, ['start']);
  release(); await Promise.all([start, stop, cancel]);
  assert.deepEqual(calls, ['start', 'stop', 'cancel']);
  const failed = []; const recover = queue(async action => { failed.push(action); if(action==='start') throw new Error('disconnected'); });
  await assert.rejects(recover('start')); await recover('cancel');
  assert.deepEqual(failed, ['start','cancel']);
  console.log('Voice queue: delayed start/release/cancel and failed start recovery pass');
})();
