'use strict';
// Keep a quick release/cancel behind its start request. No command is retried:
// a lost response must not start a second microphone capture.
function createVoiceQueue(run) {
  let tail = Promise.resolve();
  return action => {
    const result = tail.catch(() => {}).then(() => run(action));
    tail = result;
    return result;
  };
}
if (typeof module !== 'undefined' && module.exports) module.exports = createVoiceQueue;
else window.createVoiceQueue = createVoiceQueue;
