import * as React from "react";
import { Loader2, Pause, Play } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { fetchAuthenticatedBlob, getApiBaseUrl, sanitizeUserError } from "@/lib/api";

type Props = {
  playPath: string | null | undefined;
  durationLabel?: string;
  compact?: boolean;
};

export function InterviewRecordingPlayer({ playPath, durationLabel, compact }: Props) {
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const [src, setSrc] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [playing, setPlaying] = React.useState(false);
  const [progress, setProgress] = React.useState(0);

  React.useEffect(() => {
    return () => {
      if (src) URL.revokeObjectURL(src);
    };
  }, [src]);

  const loadAudio = async () => {
    if (!playPath || src) return src;
    setLoading(true);
    try {
      const blob = await fetchAuthenticatedBlob(playPath);
      const url = URL.createObjectURL(blob);
      setSrc(url);
      return url;
    } catch (e) {
      toast.error(sanitizeUserError(e instanceof Error ? e.message : "Recording not available yet"));
      return null;
    } finally {
      setLoading(false);
    }
  };

  const toggle = async () => {
    let url = src;
    if (!url) url = await loadAudio();
    if (!url) return;
    let audio = audioRef.current;
    if (!audio) {
      audio = new Audio(url);
      audioRef.current = audio;
      audio.addEventListener("timeupdate", () => {
        if (!audio.duration) return;
        setProgress(Math.round((audio.currentTime / audio.duration) * 100));
      });
      audio.addEventListener("ended", () => setPlaying(false));
      audio.addEventListener("pause", () => setPlaying(false));
      audio.addEventListener("play", () => setPlaying(true));
    }
    if (playing) {
      audio.pause();
    } else {
      void audio.play();
    }
  };

  if (!playPath) {
    return <span className="text-xs text-muted-foreground">No recording</span>;
  }

  return (
    <div className={`flex items-center gap-2 ${compact ? "" : "rounded-lg border border-border bg-muted/40 p-3"}`}>
      <Button size="icon" className="size-9 shrink-0 rounded-full" variant={compact ? "ghost" : "default"} onClick={() => void toggle()} disabled={loading}>
        {loading ? <Loader2 className="size-4 animate-spin" /> : playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      </Button>
      {!compact && (
        <div className="min-w-0 flex-1">
          <div className="h-1.5 overflow-hidden rounded-full bg-border">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {durationLabel || "—"} · Interview recording
            {getApiBaseUrl() ? "" : " (local API)"}
          </p>
        </div>
      )}
    </div>
  );
}
