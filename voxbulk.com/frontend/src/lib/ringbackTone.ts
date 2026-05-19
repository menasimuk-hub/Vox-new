/**
 * Soft UK-style ringback (dual-tone bursts) while the voice agent connects.
 * Uses Web Audio so we don't ship a separate audio asset.
 */

export type RingbackController = {
  start: () => void;
  stop: (fadeMs?: number) => void;
  isPlaying: () => boolean;
};

const RING_FREQ_A = 425;
const RING_FREQ_B = 475;
const BURST_MS = 380;
const GAP_MS = 180;
const CYCLE_MS = 3200;
const VOLUME = 0.11;

export function createRingbackTone(): RingbackController {
  let audioContext: AudioContext | null = null;
  let masterGain: GainNode | null = null;
  let cycleTimer: number | null = null;
  let burstTimers: number[] = [];
  let playing = false;

  const clearBurstTimers = () => {
    burstTimers.forEach((id) => window.clearTimeout(id));
    burstTimers = [];
  };

  const playBurst = () => {
    if (!audioContext || !masterGain || !playing) return;
    const ctx = audioContext;
    const now = ctx.currentTime;
    const duration = BURST_MS / 1000;
    const env = ctx.createGain();
    env.gain.setValueAtTime(0.0001, now);
    env.gain.exponentialRampToValueAtTime(1, now + 0.02);
    env.gain.setValueAtTime(1, now + duration - 0.04);
    env.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    env.connect(masterGain);

    const oscA = ctx.createOscillator();
    oscA.type = "sine";
    oscA.frequency.value = RING_FREQ_A;
    const oscB = ctx.createOscillator();
    oscB.type = "sine";
    oscB.frequency.value = RING_FREQ_B;
    oscA.connect(env);
    oscB.connect(env);
    oscA.start(now);
    oscB.start(now);
    oscA.stop(now + duration);
    oscB.stop(now + duration);
  };

  const playCycle = () => {
    if (!playing) return;
    playBurst();
    burstTimers.push(
      window.setTimeout(() => {
        if (!playing) return;
        playBurst();
      }, BURST_MS + GAP_MS),
    );
  };

  return {
    start() {
      if (playing) return;
      playing = true;
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctx) return;
      audioContext = new Ctx();
      masterGain = audioContext.createGain();
      masterGain.gain.value = VOLUME;
      masterGain.connect(audioContext.destination);
      void audioContext.resume().catch(() => undefined);
      playCycle();
      cycleTimer = window.setInterval(playCycle, CYCLE_MS);
    },

    stop(fadeMs = 180) {
      if (!playing) return;
      playing = false;
      clearBurstTimers();
      if (cycleTimer !== null) {
        window.clearInterval(cycleTimer);
        cycleTimer = null;
      }
      const ctx = audioContext;
      const gain = masterGain;
      audioContext = null;
      masterGain = null;
      if (!ctx || !gain) return;
      const now = ctx.currentTime;
      const fadeSec = Math.max(0.05, fadeMs / 1000);
      try {
        gain.gain.cancelScheduledValues(now);
        gain.gain.setValueAtTime(gain.gain.value, now);
        gain.gain.linearRampToValueAtTime(0, now + fadeSec);
      } catch {
        gain.gain.value = 0;
      }
      window.setTimeout(() => {
        void ctx.close().catch(() => undefined);
      }, fadeMs + 40);
    },

    isPlaying() {
      return playing;
    },
  };
}
