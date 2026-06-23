type TranscriptPanelProps = {
  transcript: string;
};

export default function TranscriptPanel({ transcript }: TranscriptPanelProps) {
  return (
    <section className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-100">
      <p className="text-sm font-semibold text-slate-500">I heard:</p>
      <p className="mt-2 text-lg font-medium leading-relaxed text-slate-900">
        {transcript}
      </p>
    </section>
  );
}
