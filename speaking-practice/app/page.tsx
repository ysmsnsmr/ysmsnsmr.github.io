"use client";

import { useState } from "react";
import InterviewPracticeCard from "@/components/InterviewPracticeCard";
import SpeakingCard from "@/components/SpeakingCard";
import lessons from "@/data/lessonCards.json";
import type { LessonCard } from "@/types/speaking";

export default function Home() {
  const [mode, setMode] = useState<"interview" | "sentence">("interview");
  const lesson = lessons[0] as LessonCard;

  if (mode === "sentence") {
    return (
      <SpeakingCard
        lesson={lesson}
        onSwitchToInterview={() => setMode("interview")}
      />
    );
  }

  return (
    <InterviewPracticeCard
      onSwitchToSentencePractice={() => setMode("sentence")}
    />
  );
}
