const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class FakeAudioContext {
  sampleRate = 44100;
  createGain() {
    return { gain: { value: 1 } };
  }
  createBuffer(channels, length, sampleRate) {
    const samples = new Float32Array(length);
    return {
      length,
      sampleRate,
      duration: length / sampleRate,
      getChannelData: () => samples,
    };
  }
}

const html = fs.readFileSync(path.join(__dirname, 'original.html'), 'utf8');
const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
  .map((match) => match[1]);
const makerIndex = scripts.findIndex((script) => script.includes('MusicMaker.createMusic ='));
assert.ok(makerIndex >= 0, 'MusicMaker script found');
const context = vm.createContext({ AudioContext: FakeAudioContext });
for (const script of scripts.slice(0, makerIndex + 1)) {
  vm.runInContext(script, context);
}
vm.runInContext(scripts.find((script) => script.includes('Sequencer.prototype.build =')), context);

function render(notes) {
  return renderSheet(`- Main\n~sin1\n*100\n${notes}`);
}

function renderSheet(sheet) {
  const result = vm.runInContext(`MusicMaker.createMusic(${JSON.stringify(sheet)})`, context);
  return result.sound.getBuffer();
}

function collectNotes(sheet) {
  const events = [];
  context.onTestNote = (...args) => events.push({
    channel: args[0],
    channelVolume: args[1],
    volume: args[2],
    speed: args[3],
    time: args[6],
    scale: args[7],
    length: args[8],
    wave: args[9],
    adsr: [...args[10]],
  });
  vm.runInContext(`MusicMaker.createMusic(${JSON.stringify(sheet)}, null, onTestNote)`, context);
  delete context.onTestNote;
  return events;
}

function rms(samples, start, length = 0.08) {
  const from = Math.floor(start * 44100);
  const count = Math.floor(length * 44100);
  let sum = 0;
  for (let i = from; i < from + count; i++) sum += samples[i] ** 2;
  return Math.sqrt(sum / count);
}

function amplitudeAt(samples, start, frequency, length = 0.1) {
  const from = Math.floor(start * 44100);
  const count = Math.floor(length * 44100);
  let real = 0;
  let imag = 0;
  for (let i = 0; i < count; i++) {
    const angle = (2 * Math.PI * frequency * i) / 44100;
    real += samples[from + i] * Math.cos(angle);
    imag += samples[from + i] * Math.sin(angle);
  }
  return Math.hypot(real, imag) / count;
}

const tones = [261.63, 329.63, 392];

test('C, E, G play sequentially at the requested times and pitches', () => {
  const samples = render('c4 3 0 2 e4 3 0 2 g4 3 0');
  assert.ok(samples.length >= 1.25 * 44100);
  for (const [time, pitch] of [[0.1, 0], [0.6, 1], [1.1, 2]]) {
    const amplitudes = tones.map((tone) => amplitudeAt(samples, time, tone));
    assert.equal(amplitudes.indexOf(Math.max(...amplitudes)), pitch);
    assert.ok(rms(samples, time) > 0.1);
  }
  assert.ok(rms(samples, 0.36) < 0.001);
  assert.ok(rms(samples, 0.86) < 0.001);
});

test('loop repeats C, E, G three times', () => {
  const samples = render('(3 c4 2 0 e4 2 0 g4 2 0 )');
  assert.ok(samples.length >= 1.7 * 44100);
  for (let repeat = 0; repeat < 3; repeat++) {
    for (let pitch = 0; pitch < 3; pitch++) {
      const time = repeat * 0.6 + pitch * 0.2 + 0.05;
      const amplitudes = tones.map((tone) => amplitudeAt(samples, time, tone));
      assert.equal(amplitudes.indexOf(Math.max(...amplitudes)), pitch);
    }
  }
});

test('documented brace loop matches its expanded notes', () => {
  const repeated = render('{2 c4 1 0}');
  const expanded = render('c4 1 0 c4 1 0');
  assert.equal(repeated.length, expanded.length);
  for (let i = 0; i < repeated.length; i++) {
    assert.equal(repeated[i], expanded[i]);
  }
});

test('nested brace loops preserve note order', () => {
  const samples = render('{2 c4 2 0 {2 e4 2 0} g4 2 0}');
  assert.ok(samples.length >= 1.55 * 44100);
  for (let repeat = 0; repeat < 2; repeat++) {
    for (const [offset, pitch] of [[0.05, 0], [0.25, 1], [0.45, 1], [0.65, 2]]) {
      const amplitudes = tones.map((tone) => amplitudeAt(samples, repeat * 0.8 + offset, tone));
      assert.equal(amplitudes.indexOf(Math.max(...amplitudes)), pitch);
    }
  }
});

test('score-only sine harmonics produce a decaying piano-like tone', () => {
  const samples = renderSheet(
    '- Main\n~sin1:1 +sin1.002:0.18 +sin2.003:0.32 +sin3.009:0.13 +sin4.018:0.07 +sin5.03:0.035\n' +
    '!a3 !d500 !s10 !r180\n*bpm120\nc4 8 8',
  );
  assert.ok(rms(samples, 0.05) > 0.1);
  assert.ok(amplitudeAt(samples, 0.05, 523.25) > 0.01);
  assert.ok(rms(samples, 0.8) < rms(samples, 0.05));
});

test('per-note MIDI velocity scales notes in a chord independently', () => {
  const notes = collectNotes('- Main\n~sin1\n*100\nc4/32 e4/127 4 0');
  assert.equal(notes.length, 2);
  assert.ok(Math.abs(notes[0].volume - 32 / 127) < 1e-12);
  assert.equal(notes[1].volume, 1);
});

test('C, E, G play together as one chord', () => {
  const samples = render('c4 e4 g4 4 0');
  assert.ok(samples.length >= 0.39 * 44100);
  const amplitudes = tones.map((tone) => amplitudeAt(samples, 0.1, tone));
  assert.ok(amplitudes.every((value) => value > 0.05), amplitudes.join(', '));
});

test('channel declarations keep wave and tempo settings independent', () => {
  const notes = collectNotes('- Main\n~sqr1\n*100\nc4 2 0\n- Sub\n~tri1\n*200\ne4 2 0');
  assert.equal(notes.length, 2);
  assert.deepEqual(notes.map((note) => [note.channel, note.speed, note.wave]), [
    [0, 100, '+sqr1:1'],
    [1, 200, '+tri1:1'],
  ]);
});

test('documented volume and ADSR commands reach the generated note', () => {
  const notes = collectNotes('- Main\n~sin1\n!0.6 %50 [a]100 [d]100 [s]30 [r]400 c4 2 0');
  assert.equal(notes.length, 1);
  assert.equal(notes[0].volume, 0.6);
  assert.equal(notes[0].channelVolume, 0.5);
  assert.deepEqual(notes[0].adsr, [100, 100, 30, 400]);
});

test('underscore encodes a negative delayed-chord offset', () => {
  const notes = collectNotes('- Main\n~sin1\n*100\nc4 e4 g4 4:1:_1 0');
  assert.equal(notes.length, 3);
  assert.deepEqual(notes.map((note) => Math.round(note.time * 1000)), [0, 100, 200]);
  assert.deepEqual(notes.map((note) => Math.round(note.length * 1000)), [400, 200, 0]);
});

test('sweep plays the white keys from C through E', () => {
  const notes = collectNotes('- Main\n~sin1\n*100\nc4:e4 8 0');
  assert.deepEqual(notes.map((note) => note.scale), [48, 50, 52]);
  assert.ok(notes[0].time < notes[1].time && notes[1].time < notes[2].time);
});

test('tutorial notes finish together after staggered starts', () => {
  const notes = collectNotes('- Main\n~sqr1\n*100\nc4 5 1 e4 4 1 g4 3 0');
  assert.deepEqual(notes.map((note) => Math.round(note.time * 1000)), [0, 100, 200]);
  assert.deepEqual(notes.map((note) => Math.round(note.length * 1000)), [500, 400, 300]);
});

test('sharp notes and octave offsets follow the documented pitch rules', () => {
  const notes = collectNotes('- Main\n~sin1\n*100\nc#4 1 0 ^1 c4 1 0 v4 c4 1 0');
  assert.deepEqual(notes.map((note) => note.scale), [49, 60, 12]);
});

test('BPM tempo and delayed chord formulas set note timings', () => {
  const notes = collectNotes('- Main\n~sin1\n*bpm120\nc4 d4 e4 4:0.1:0.1 0');
  assert.equal(notes.length, 3);
  assert.ok(Math.abs(notes[0].speed - 125) < 0.001);
  assert.deepEqual(notes.map((note) => Math.round(note.time * 1000)), [0, 13, 25]);
  assert.deepEqual(notes.map((note) => Math.round(note.length * 1000)), [475, 475, 475]);
});

test('title, inline, and angle-bracket comments do not create notes', () => {
  const notes = collectNotes('$ Title\n- Main\n~sin1\n*100\nc4 2 0 $ ignore d4 2 0\n< ignore f4 2 0 > e4 2 0');
  assert.deepEqual(notes.map((note) => note.scale), [48, 52]);
});

test('declared waveform and modulation graph produce audible samples', () => {
  const samples = renderSheet('- Main\n&TestWave:sin:100 &TestNote:tri\n[TestWave:200 > TestNote]\n~TestNote\n*100\nc4 4 0');
  assert.ok(samples.length >= 0.39 * 44100);
  assert.ok(rms(samples, 0.1) > 0.01);
  assert.ok([...samples].every(Number.isFinite));
});

test('nested waveform graph produces audible samples', () => {
  const samples = renderSheet('- Main\n&A:sin:100 &B:sqr:150 &C:tri\n[[A:0.5 + B:0.5]:100 > C]\n~C\n*100\nc4 4 0');
  assert.ok(samples.length >= 0.39 * 44100);
  assert.ok(rms(samples, 0.1) > 0.01);
  assert.ok([...samples].every(Number.isFinite));
});

test('waveform mix uses the documented weighted sum', () => {
  const value = vm.runInContext(`(() => {
    const mix = new OpNodeConv();
    mix.parents = [{ calculate: () => 1 }, { calculate: () => 1 }];
    mix.scales = [0.5, 0.5];
    return mix.calculate(0, 440, 0, []);
  })()`, context);
  assert.equal(value, 1);
});

test('low-pass, high-pass, feedback, and noise graph waves stay finite', () => {
  const sheets = [
    '- Main\n&A:sin:100 &F:low:1000\n[A:1 > F]\n~F\n*100\nc4 4 0',
    '- Main\n&A:sin:100 &F:high:1000\n[A:1 > F]\n~F\n*100\nc4 4 0',
    '- Main\n&A:sin:100 &F:feedback:0.3\n[A > F]\n~F\n*100\nc4 4 0',
    '- Main\n~noise\n*100\nc4 4 0',
  ];
  for (const sheet of sheets) {
    const samples = renderSheet(sheet);
    assert.ok(samples.length >= 0.39 * 44100);
    assert.ok(rms(samples, 0.1) > 0.001);
    assert.ok([...samples].every(Number.isFinite));
  }
});

test('inline waveform declaration matches the documented tilde syntax', () => {
  const samples = renderSheet('- Main\n~TestWave:sin:100 +TestWave:0.5\n*100\nc4 4 0');
  assert.ok(samples.length >= 0.39 * 44100);
  assert.ok(rms(samples, 0.1) > 0.01);
  assert.ok([...samples].every(Number.isFinite));
});

test('saving a new score makes it available to previous and next navigation', () => {
  context.window = { localStorage: {} };
  const result = vm.runInContext(`(() => {
    MusicList.saveSheet(0, '$ First');
    MusicList.saveSheet(0, '$ First updated');
    MusicList.saveSheet(1, '$ Second');
    return [MusicList.getCount(), MusicList.getSheet(0), MusicList.getSheet(1)];
  })()`, context);
  assert.deepEqual([...result], [2, '$ First updated', '$ Second']);
});

test('sequencer export preserves simultaneous notes and later starts', () => {
  const lines = Array.from({ length: 72 }, () => []);
  lines[48].push({ time: 0, beat: 4 });
  lines[52].push({ time: 0, beat: 2 });
  lines[55].push({ time: 3, beat: 3 });
  context.seqFixture = {
    lines,
    minOctave: 0,
    indexToName: ['c', 'c#', 'd', 'd#', 'e', 'f', 'f#', 'g', 'g#', 'a', 'a#', 'b'],
    volumeSeq: { volumes: [{ time: 0, volume: 1 }] },
  };
  const code = vm.runInContext('Sequencer.prototype.build.call(seqFixture)', context);
  const notes = collectNotes('- Main\n~sin1\n*100\n' + code);
  assert.deepEqual(notes.map((note) => [note.scale, Math.round(note.time * 1000), Math.round(note.length * 1000)]), [
    [52, 0, 200],
    [48, 0, 400],
    [55, 300, 300],
  ]);
});
