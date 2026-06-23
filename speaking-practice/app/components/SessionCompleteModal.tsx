import type { ProgressRecord } from "@/types/speaking";

type SessionCompleteModalProps = {
  progress: ProgressRecord;
  onRestart: () => void;
};

export default function SessionCompleteModal({
  progress,
  onRestart
}: SessionCompleteModalProps) {
  return (
    <div className="fixed inset-0 z-30 flex items-end bg-slate-950/30 px-4 pb-4 backdrop-blur-sm sm:items-center sm:justify-center">
      <section className="mx-auto w-full max-w-md rounded-lg bg-white p-6 text-center shadow-soft">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-honey/25">
          <span className="h-8 w-8 rounded-full bg-honey" aria-hidden="true" />
        </div>
        <h2 className="mt-4 text-2xl font-bold text-slate-950">
          Done for today
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          You spoke {progress.sentenceCount}{" "}
          {progress.sentenceCount === 1 ? "time" : "times"} today.
        </p>
        <div className="mt-5 flex justify-center gap-2">
          {progress.streakDots.map((active, index) => (
            <span
              key={index}
              className={[
                "h-3 w-3 rounded-full",
                active ? "bg-calm" : "bg-slate-200"
              ].join(" ")}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={onRestart}
          className="mt-6 w-full rounded-full bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition active:scale-[0.99]"
        >
          Practice once more
        </button>
      </section>
    </div>
  );
}
