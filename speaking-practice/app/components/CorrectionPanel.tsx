type CorrectionPanelProps = {
  transcript: string;
  correction: string;
  onContinue: () => void;
};

export default function CorrectionPanel({
  transcript,
  correction,
  onContinue
}: CorrectionPanelProps) {
  return (
    <section className="space-y-3">
      <div className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-100">
        <p className="text-sm font-semibold text-slate-500">I heard:</p>
        <p className="mt-2 text-base font-medium text-slate-800">{transcript}</p>
      </div>
      <div className="rounded-lg bg-calm-soft p-4 shadow-sm">
        <p className="text-sm font-semibold text-calm">Try this:</p>
        <p className="mt-1 text-xl font-bold leading-snug text-slate-950">
          {correction}
        </p>
      </div>
      <button
        type="button"
        onClick={onContinue}
        className="w-full rounded-full bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition active:scale-[0.99]"
      >
        Practice this sentence
      </button>
    </section>
  );
}
