import { toast } from "sonner";

type Props = {
  online: boolean;
  setOnline: (v: boolean | ((p: boolean) => boolean)) => void;
  lang: "en" | "ar";
};

export function OnlineSlider({ online, setOnline, lang }: Props) {
  const isAr = lang === "ar";
  const onLabel = isAr ? "متصل" : "ONLINE";
  const offLabel = isAr ? "غير متصل" : "OFFLINE";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={online}
      onClick={() => {
        setOnline(v => !v);
        toast.success(
          online
            ? isAr
              ? "أنت الآن غير متصل"
              : "You are now Offline"
            : isAr
            ? "أنت الآن متصل"
            : "You are now Online",
        );
      }}
      className={`relative inline-flex h-9 items-center rounded-full px-3 py-1.5 transition-all duration-300 border ${
        online
          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
          : "bg-zinc-100 border-zinc-200 dark:bg-zinc-800 dark:border-zinc-700 text-zinc-500"
      }`}
    >
      <span className="flex items-center gap-2">
        <span className="relative flex h-2.5 w-2.5">
          {online && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          )}
          <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${online ? "bg-emerald-500" : "bg-zinc-400"}`} />
        </span>
        <span className="text-xs font-bold tracking-wide uppercase select-none">
          {online ? onLabel : offLabel}
        </span>
      </span>
    </button>
  );
}
