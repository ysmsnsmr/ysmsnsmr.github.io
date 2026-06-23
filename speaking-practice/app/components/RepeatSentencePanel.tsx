import SentencePlayer from "@/components/SentencePlayer";

type RepeatSentencePanelProps = {
  sentence: string;
};

export default function RepeatSentencePanel({ sentence }: RepeatSentencePanelProps) {
  return (
    <section className="rounded-lg bg-white p-6 text-center shadow-soft ring-1 ring-white/70">
      <h1 className="text-2xl font-bold leading-snug text-slate-950">
        {sentence}
      </h1>
      <div className="mt-4 flex justify-center">
        <SentencePlayer sentence={sentence} compact />
      </div>
      <p className="mt-4 text-xs font-medium text-slate-500">Say it slowly.</p>
    </section>
  );
}
