type UnclearSpeechPanelProps = {
  onTryAgain: () => void;
};

export default function UnclearSpeechPanel({ onTryAgain }: UnclearSpeechPanelProps) {
  return (
    <section className="rounded-lg bg-white p-5 shadow-sm ring-1 ring-slate-100">
      <p className="text-lg font-bold leading-snug text-slate-900">
        I could not hear that clearly. Let&apos;s try once more.
      </p>
      <p className="mt-3 rounded-lg bg-honey/20 px-3 py-2 text-sm font-medium text-slate-700">
        Try speaking a little closer to the mic.
      </p>
      <button
        type="button"
        onClick={onTryAgain}
        className="mt-5 w-full rounded-full bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition active:scale-[0.99]"
      >
        Try again
      </button>
    </section>
  );
}
