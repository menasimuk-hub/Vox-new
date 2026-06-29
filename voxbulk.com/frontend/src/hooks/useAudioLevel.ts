import { useEffect, useState } from "react";

/** Normalized 0–1 audio level from a MediaStream (for speaking indicators). */
export function useAudioLevel(stream: MediaStream | null | undefined, enabled = true): number {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!enabled || !stream) {
      setLevel(0);
      return;
    }
    let raf = 0;
    let ctx: AudioContext | null = null;
    try {
      ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.75;
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i];
        setLevel(sum / data.length / 255);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    } catch {
      setLevel(0);
    }
    return () => {
      cancelAnimationFrame(raf);
      void ctx?.close().catch(() => {});
    };
  }, [stream, enabled]);

  return level;
}
