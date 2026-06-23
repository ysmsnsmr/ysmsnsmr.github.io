"use client";

import { useEffect, useRef, useState } from "react";
import CorrectionPanel from "@/components/CorrectionPanel";
import MicButton from "@/components/MicButton";
import RepeatSentencePanel from "@/components/RepeatSentencePanel";
import SentencePlayer from "@/components/SentencePlayer";
import SessionCompleteModal from "@/components/SessionCompleteModal";
import TranscriptPanel from "@/components/TranscriptPanel";
import UnclearSpeechPanel from "@/components/UnclearSpeechPanel";
import WaveformIndicator from "@/components/WaveformIndicator";
import {
  acceptPrivacyNotice,
  completeCard,
  defaultProgress,
  loadProgress
} from "@/lib/progress";
import type {
  FeedbackResult,
  LessonCard,
  MicState,
  ProgressRecord,
  SpeakingState
} from "@/types/speaking";

type SpeakingCardProps = {
  lesson: LessonCard;
  onSwitchToInterview?: () => void;
};

const minimumClearRecordingMs = 800;

export default function SpeakingCard({
  lesson,
  onSwitchToInterview
}: SpeakingCardProps) {
  const [state, setState] = useState<SpeakingState>("idle");
  const [feedback, setFeedback] = useState<FeedbackResult | null>(null);
  const [progress, setProgress] = useState<ProgressRecord>(defaultProgress);
  const [showPrivacyNotice, setShowPrivacyNotice] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [hasCompleted, setHasCompleted] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef<number>(0);
  const repeatAttemptRef = useRef(false);
  const armingTimerRef = useRef<number | null>(null);

  useEffect(() => {
    const storedProgress = loadProgress();
    setProgress(storedProgress);
    setShowPrivacyNotice(!storedProgress.privacyNoticeAccepted);

    return () => {
      if (armingTimerRef.current) {
        window.clearTimeout(armingTimerRef.current);
      }
      stopStream();
    };
  }, []);

  const micState: MicState =
    state === "arming" || state === "recording" || state === "processing"
      ? state
      : "idle";
  const showMicDock =
    !hasCompleted &&
    (state === "idle" ||
      state === "arming" ||
      state === "recording" ||
      state === "processing" ||
      state === "repeat");

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function handleAcceptPrivacyNotice() {
    const nextProgress = acceptPrivacyNotice();
    setProgress(nextProgress);
    setShowPrivacyNotice(false);
  }

  function handleBack() {
    setState("idle");
    setFeedback(null);
    setStatusMessage(null);
    repeatAttemptRef.current = false;
  }

  function handleMicPress() {
    if (state === "recording") {
      stopRecording();
      return;
    }

    if (state === "processing" || state === "arming") {
      return;
    }

    repeatAttemptRef.current = state === "repeat";
    startArming();
  }

  function startArming() {
    setStatusMessage(null);
    setState("arming");
    armingTimerRef.current = window.setTimeout(() => {
      void startRecording();
    }, 450);
  }

  async function startRecording() {
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setState("unclear");
      setStatusMessage("Try using a browser with microphone support.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];
      recordingStartedAtRef.current = Date.now();

      const options = MediaRecorder.isTypeSupported("audio/webm")
        ? { mimeType: "audio/webm" }
        : undefined;
      const recorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onstop = () => {
        const durationMs = Date.now() - recordingStartedAtRef.current;
        const audioBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm"
        });
        chunksRef.current = [];
        stopStream();
        void handleRecordingComplete(audioBlob, durationMs, repeatAttemptRef.current);
      };

      recorder.start();
      setState("recording");
    } catch {
      stopStream();
      setState("unclear");
      setStatusMessage("Try allowing microphone access, then tap the mic again.");
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    setState("processing");

    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      return;
    }

    void handleRecordingComplete(null, 0, repeatAttemptRef.current);
  }

  async function handleRecordingComplete(
    audioBlob: Blob | null,
    durationMs: number,
    isRepeatAttempt: boolean
  ) {
    if (durationMs < minimumClearRecordingMs) {
      setState("unclear");
      setStatusMessage(null);
      return;
    }

    if (isRepeatAttempt) {
      const nextProgress = completeCard(lesson.id);
      setProgress(nextProgress);
      setHasCompleted(true);
      setState("success");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("lessonId", lesson.id);
      if (audioBlob) {
        formData.append("audio", audioBlob, "practice.webm");
      }

      const response = await fetch("/api/speaking-feedback", {
        method: "POST",
        body: formData
      });
      const result = (await response.json()) as FeedbackResult;
      setFeedback(result);
      setState(result.clarity === "unclear" ? "unclear" : "transcript");
    } catch {
      setState("unclear");
      setStatusMessage("Let's try that once more.");
    }
  }

  function handleShowCorrection() {
    setState("correction");
  }

  function handleRepeatReady() {
    setState("repeat");
  }

  function handleTryAgain() {
    setState("idle");
    setStatusMessage(null);
  }

  function handleRestart() {
    setHasCompleted(false);
    setFeedback(null);
    repeatAttemptRef.current = false;
    setState("idle");
  }

  const showStandardCard =
    state === "idle" ||
    state === "arming" ||
    state === "recording" ||
    state === "processing" ||
    state === "transcript";

  return (
    <main className="min-h-dvh bg-[radial-gradient(circle_at_top,#FFF7DD_0,#F8F4EA_42%,#EEF8F6_100%)] px-4 py-5">
      <div
        className={[
          "mx-auto flex min-h-[calc(100dvh-40px)] max-w-md flex-col",
          showMicDock ? "pb-56" : "pb-8"
        ].join(" ")}
      >
        <header className="mb-4 flex items-center justify-between">
          <button
            type="button"
            onClick={onSwitchToInterview ?? handleBack}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-lg font-bold text-slate-600 shadow-sm ring-1 ring-slate-100"
            aria-label={onSwitchToInterview ? "Back to interview practice" : "Back"}
          >
            <span aria-hidden="true">‹</span>
          </button>
          <p className="rounded-full bg-white/80 px-3 py-1 text-sm font-semibold text-slate-500 shadow-sm">
            Card 1 / 1
          </p>
          <button
            type="button"
            onClick={() => setShowPrivacyNotice(true)}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-sm font-bold text-calm shadow-sm ring-1 ring-slate-100"
            aria-label="Help"
          >
            ?
          </button>
        </header>

        <div className="space-y-4">
          {showStandardCard && (
            <section className="rounded-lg bg-white p-5 shadow-soft ring-1 ring-white/70">
              <div className="flex items-center justify-between gap-3">
                <p className="rounded-full bg-calm-soft px-3 py-1 text-xs font-bold uppercase tracking-[0.08em] text-calm">
                  {lesson.scenario}
                </p>
                <p className="text-xs font-semibold text-slate-400">{lesson.level}</p>
              </div>
              <h1 className="mt-4 text-3xl font-bold leading-tight text-slate-950">
                {lesson.sentence}
              </h1>
              <SentencePlayer
                sentence={lesson.sentence}
                japaneseHint={lesson.japaneseHint}
              />
            </section>
          )}

          {state === "idle" && (
            <section className="rounded-lg bg-white/75 p-4 text-sm leading-relaxed text-slate-600 ring-1 ring-white">
              Listen first, then say the sentence out loud.
            </section>
          )}

          {state === "transcript" && feedback && (
            <section className="space-y-3">
              <TranscriptPanel transcript={feedback.transcript} />
              <button
                type="button"
                onClick={handleShowCorrection}
                className="w-full rounded-full bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition active:scale-[0.99]"
              >
                Show me how to say it
              </button>
            </section>
          )}

          {state === "correction" && feedback && (
            <CorrectionPanel
              transcript={feedback.transcript}
              correction={feedback.correction}
              onContinue={handleRepeatReady}
            />
          )}

          {state === "repeat" && feedback && (
            <RepeatSentencePanel sentence={feedback.correction} />
          )}

          {state === "unclear" && (
            <UnclearSpeechPanel onTryAgain={handleTryAgain} />
          )}

          {statusMessage && (
            <p className="rounded-lg bg-white px-4 py-3 text-sm font-medium text-slate-600 shadow-sm">
              {statusMessage}
            </p>
          )}
        </div>
      </div>

      {showMicDock && (
        <div className="fixed inset-x-0 bottom-0 z-20 bg-gradient-to-t from-paper via-paper to-paper/0 px-4 pb-[calc(env(safe-area-inset-bottom)+1rem)] pt-10">
          <div className="mx-auto max-w-md rounded-lg bg-white/90 px-4 pb-4 pt-2 shadow-soft ring-1 ring-white/80 backdrop-blur">
            <WaveformIndicator
              active={state === "recording"}
              subdued={state === "processing"}
            />
            <MicButton
              state={micState}
              onPress={handleMicPress}
              disabled={showPrivacyNotice || hasCompleted}
              idleLabel={state === "repeat" ? "Say it again" : undefined}
            />
          </div>
        </div>
      )}

      {showPrivacyNotice && (
        <div className="fixed inset-0 z-40 flex items-end bg-slate-950/30 px-4 pb-4 backdrop-blur-sm sm:items-center sm:justify-center">
          <section className="mx-auto w-full max-w-md rounded-lg bg-white p-6 shadow-soft">
            <p className="text-sm font-bold uppercase tracking-[0.08em] text-calm">
              Parent privacy note
            </p>
            <h2 className="mt-2 text-2xl font-bold leading-tight text-slate-950">
              Microphone practice stays simple.
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              This MVP uses the microphone only after the mic is tapped. Audio is
              sent to the local mock practice route for that attempt only and is
              not saved. Progress stays on this device.
            </p>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              Stored progress includes completed card IDs, practice date,
              sentence count, and streak dots.
            </p>
            <button
              type="button"
              onClick={handleAcceptPrivacyNotice}
              className="mt-6 w-full rounded-full bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition active:scale-[0.99]"
            >
              I understand
            </button>
          </section>
        </div>
      )}

      {state === "success" && hasCompleted && (
        <SessionCompleteModal progress={progress} onRestart={handleRestart} />
      )}
    </main>
  );
}
