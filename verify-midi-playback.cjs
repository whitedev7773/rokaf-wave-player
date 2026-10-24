const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const scorePath = process.argv[2];
if (!scorePath) throw new Error('Usage: node verify-midi-playback.cjs SCORE.seq');
const html = fs.readFileSync(path.join(__dirname, 'original.html'), 'utf8');
const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
  .map((match) => match[1]);
const makerIndex = scripts.findIndex((script) => script.includes('MusicMaker.createMusic ='));
const events = [];
const context = vm.createContext({
  AudioContext: class {
    sampleRate = 44100;
    createGain() { return { gain: { value: 1 } }; }
    createBuffer(channels, length, sampleRate) {
      return { length, sampleRate, getChannelData: () => new Float32Array(length) };
    }
  },
  recordNote: (...args) => events.push({
    channel: args[0],
    time: args[6],
    scale: args[7],
    length: args[8],
  }),
});
for (const script of scripts.slice(0, makerIndex + 1)) vm.runInContext(script, context);
context.score = fs.readFileSync(scorePath, 'utf8');
vm.runInContext('MusicMaker.createMusic(score, null, recordNote)', context);
events.sort((a, b) => a.time - b.time || a.scale - b.scale || a.length - b.length);
const report = {
  noteCount: events.length,
  sequenceCount: new Set(events.map((event) => event.channel)).size,
  first: events.slice(0, 6),
  lastEndSeconds: Math.max(...events.map((event) => event.time + event.length)),
};
if (process.argv[3]) {
  const expected = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
  if (events.length !== expected.length) throw new Error(`note count ${events.length} != ${expected.length}`);
  const actualByPitch = new Map();
  const expectedByPitch = new Map();
  for (const event of events) {
    const pitch = event.scale + 12;
    if (!actualByPitch.has(pitch)) actualByPitch.set(pitch, []);
    actualByPitch.get(pitch).push([event.time, event.time + event.length]);
  }
  for (const note of expected) {
    if (!expectedByPitch.has(note[0])) expectedByPitch.set(note[0], []);
    expectedByPitch.get(note[0]).push([note[1], note[2]]);
  }
  let maxTimingErrorSeconds = 0;
  for (const [pitch, actualNotes] of actualByPitch) {
    const expectedNotes = expectedByPitch.get(pitch) || [];
    if (actualNotes.length !== expectedNotes.length) throw new Error(`pitch ${pitch} count mismatch`);
    const sortNotes = (a, b) => a[0] - b[0] || a[1] - b[1];
    actualNotes.sort(sortNotes);
    expectedNotes.sort(sortNotes);
    for (let i = 0; i < actualNotes.length; i++) {
      maxTimingErrorSeconds = Math.max(maxTimingErrorSeconds,
        Math.abs(actualNotes[i][0] - expectedNotes[i][0]),
        Math.abs(actualNotes[i][1] - expectedNotes[i][1]));
    }
  }
  report.maxTimingErrorSeconds = maxTimingErrorSeconds;
  if (maxTimingErrorSeconds > 0.001) throw new Error('timing error exceeds 1 ms');
}
console.log(JSON.stringify(report, null, 2));
