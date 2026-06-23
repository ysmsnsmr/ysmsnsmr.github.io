"use client";

import { useEffect, useState } from "react";

type SentencePlayerProps = {
  sentence: string;
  japaneseHint?: string;
  compact?: boolean;
};

export default function SentencePlayer({
  sentence,
  japaneseHint,
  compact = false
}: SentencePlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [showHint, setShowHint] = useState(false);

  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  function playSentence() {
    setIsPlaying(true);

    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(sentence);
      utterance.lang = "en-US";
      utterance.rate = 0.82;
      utterance.onend = () => setIsPlaying(false);
      utterance.onerror = () => setIsPlaying(false);
      window.speechSynthesis.speak(utterance);
      return;
    }

    globalThis.setTimeout(() => setIsPlaying(false), 900);
  }

  return (
    <div className={compact ? "" : "mt-4"}>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={playSentence}
          className="rounded-full bg-calm-soft px-4 py-2 text-sm font-semibold text-calm transition hover:bg-calm-soft/80"
        >
          {isPlaying ? "Playing..." : compact ? "Listen again" : "Listen"}
        </button>
        {japaneseHint && !compact && (
          <button
            type="button"
            onClick={() => setShowHint((current) => !current)}
            className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-500 ring-1 ring-slate-200 transition hover:bg-slate-50"
          >
            Hint
          </button>
        )}
      </div>
      {showHint && japaneseHint && (
        <p className="mt-3 rounded-lg bg-honey/20 px-3 py-2 text-sm text-slate-700">
          {japaneseHint}
        </p>
      )}
    </div>
  );
}
