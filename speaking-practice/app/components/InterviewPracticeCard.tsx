"use client";

import { useEffect, useRef, useState } from "react";
import MicButton from "@/components/MicButton";
import WaveformIndicator from "@/components/WaveformIndicator";
import {
  acceptPrivacyNotice,
  completeInterviewSession,
  defaultProgress,
  loadProgress
} from "@/lib/progress";
import {
  buildLocalInterviewReview,
  focusSoundCues,
  focusSounds,
  inferGroqAudioExtension,
  isSupportedGroqAudioType,
  maxInterviewAudioBytes,
  minimumInterviewRecordingMs
} from "@/lib/interview";
import type {
  FeedbackResult,
  FocusSound,
  InterviewMaterials,
  InterviewPracticeReview,
  MicState,
  ProgressRecord,
  SttErrorCode
} from "@/types/speaking";

type InterviewPracticeCardProps = {
  onSwitchToSentencePractice: () => void;
};

type FlowState =
  | "input"
  | "generating"
  | "materials"
  | "recording"
  | "processing"
  | "review"
  | "complete";

const minimumClearRecordingMs = 800;
export default function InterviewPracticeCard({
  onSwitchToSentencePractice
}: InterviewPracticeCardProps) {
  const [flowState, setFlowState] = useState<FlowState>("input");
  const [workLog, setWorkLog] = useState("");
  const [targetRole, setTargetRole] = useState("AI-enabled sales / operations role");
  const [focusSound, setFocusSound] = useState<FocusSound>("/h/");
  const [materials, setMaterials] = useState<InterviewMaterials | null>(null);
  const [review, setReview] = useState<InterviewPracticeReview | null>(null);
  const [reviewMode, setReviewMode] = useState<"recording" | "quiet">("recording");
  const [transcriptPreview, setTranscriptPreview] = useState("");
  const [progress, setProgress] = useState<ProgressRecord>(defaultProgress);
  const [showPrivacyNotice, setShowPrivacyNotice] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef(0);

  useEffect(() => {
    const storedProgress = loadProgress();
    setProgress(storedProgress);
    setShowPrivacyNotice(!storedProgress.privacyNoticeAccepted);

    return () => {
      stopStream();
    };
  }, []);

  const micState: MicState =
    flowState === "recording"
      ? "recording"
      : flowState === "processing"
        ? "processing"
        : "idle";
  const canGenerate = workLog.trim().length > 0 && flowState !== "generating";
  const latestSession = progress.interviewSessions[0];

  function stopStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function handleAcceptPrivacyNotice() {
    const nextProgress = acceptPrivacyNotice();
    setProgress(nextProgress);
    setShowPrivacyNotice(false);
  }

  async function handleGenerateMaterials() {
    if (!canGenerate) {
      return;
    }

    setFlowState("generating");
    setStatusMessage(null);
    setReview(null);
    setTranscriptPreview("");

    try {
      const response = await fetch("/api/interview-materials", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          workLog,
          targetRole,
          focusSound
        })
      });

      if (!response.ok) {
        throw new Error("Could not generate materials");
      }

      const result = (await response.json()) as InterviewMaterials;
      setMaterials(result);
      setFlowState("materials");
    } catch {
      setStatusMessage("I could not generate materials. Please shorten the log and try again.");
      setFlowState("input");
    }
  }

  async function handleMicPress() {
    if (flowState === "recording") {
      stopRecording();
      return;
    }

    if (flowState === "processing" || !materials) {
      return;
    }

    await startRecording();
  }

  async function startRecording() {
    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setStatusMessage("Microphone recording is not available here. Use quiet mode for this session.");
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
        void handleRecordingComplete(audioBlob, durationMs);
      };

      recorder.start();
      setFlowState("recording");
      setStatusMessage(null);
    } catch {
      stopStream();
      setStatusMessage("Please allow microphone access, or finish with quiet mode today.");
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;
    setFlowState("processing");

    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
      return;
    }

    void handleRecordingComplete(null, 0);
  }

  async function handleRecordingComplete(audioBlob: Blob | null, durationMs: number) {
    if (!materials) {
      setFlowState("materials");
      return;
    }

    if (durationMs < minimumInterviewRecordingMs) {
      setStatusMessage("録音が短すぎました。もう一度録音するか、今日はquiet modeで完了してください。");
      setFlowState("materials");
      return;
    }

    if (!audioBlob || audioBlob.size === 0) {
      setStatusMessage("録音が空でした。もう一度録音するか、今日はquiet modeで完了してください。");
      setFlowState("materials");
      return;
    }

    if (audioBlob.size > maxInterviewAudioBytes) {
      setStatusMessage("録音が25MBを超えています。短く録音し直すか、今日はquiet modeで完了してください。");
      setFlowState("materials");
      return;
    }

    const audioType = audioBlob.type || "audio/webm";
    if (!isSupportedGroqAudioType(audioType)) {
      setStatusMessage("このブラウザの録音形式はMVP対象外です。Chrome/Edgeで録音するか、今日はquiet modeで完了してください。");
      setFlowState("materials");
      return;
    }

    try {
      const formData = new FormData();
      formData.append("mode", "interview");
      formData.append("materialId", materials.id);
      formData.append("focusSound", materials.focusSound);
      formData.append("answer30", materials.answer30);
      formData.append("durationMs", String(durationMs));
      formData.append("audioType", audioType);
      const audioExtension = inferGroqAudioExtension(audioType) ?? "webm";
      formData.append(
        "audio",
        audioBlob,
        `interview-practice.${audioExtension}`
      );

      const response = await fetch("/api/speaking-feedback", {
        method: "POST",
        body: formData
      });
      const result = (await response.json()) as FeedbackResult;
      if (!response.ok || result.sttStatus !== "success" || !result.review) {
        setStatusMessage(result.nextAction || getSttFailureMessage(result.sttErrorCode));
        setFlowState("materials");
        return;
      }

      setTranscriptPreview(result.transcript);
      setReview(result.review);
      setReviewMode("recording");
      setFlowState("review");
    } catch {
      setStatusMessage("Whisper文字起こしに失敗しました。音声は保存していません。もう一度録音してください。");
      setFlowState("materials");
    }
  }

  function handleQuietReview() {
    if (!materials) {
      return;
    }

    setReview(
      buildLocalInterviewReview({
        focusSound: materials.focusSound
      })
    );
    setTranscriptPreview("");
    setReviewMode("quiet");
    setFlowState("review");
    setStatusMessage(null);
  }

  function handleCompleteSession(completedMode: "recording" | "quiet") {
    if (!materials || !review) {
      return;
    }

    const nextProgress = completeInterviewSession({
      id: materials.id,
      date: new Date().toISOString().slice(0, 10),
      topic: materials.topic,
      targetRole,
      focusSound: materials.focusSound,
      answer30: materials.answer30,
      answer30Ipa: materials.answer30Ipa,
      questions: materials.questions,
      repairPhrases: materials.repairPhrases,
      pronunciationTip: materials.pronunciationTip,
      review,
      completedMode
    });
    setProgress(nextProgress);
    setFlowState("complete");
  }

  function handleStartNew() {
    setFlowState("input");
    setWorkLog("");
    setMaterials(null);
    setReview(null);
    setTranscriptPreview("");
    setReviewMode("recording");
    setStatusMessage(null);
  }

  return (
    <main className="min-h-dvh bg-[linear-gradient(135deg,#F8F4EA_0%,#EEF8F6_52%,#FFF7DD_100%)] px-4 py-5">
      <div className="mx-auto flex min-h-[calc(100dvh-40px)] max-w-2xl flex-col pb-8">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.08em] text-calm">
              Interview practice
            </p>
            <h1 className="mt-1 text-2xl font-bold leading-tight text-slate-950">
              Turn one work log into one spoken answer.
            </h1>
          </div>
          <button
            type="button"
            onClick={onSwitchToSentencePractice}
            className="rounded-full bg-white px-4 py-2 text-sm font-bold text-slate-600 shadow-sm ring-1 ring-slate-100"
          >
            Sentence mode
          </button>
        </header>

        <div className="grid gap-4">
          <section className="rounded-lg bg-white p-5 shadow-soft ring-1 ring-white/80">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-bold text-slate-950">Daily setup</p>
              <button
                type="button"
                onClick={() => setShowPrivacyNotice(true)}
                className="rounded-full bg-calm-soft px-3 py-1 text-xs font-bold text-calm"
              >
                Privacy
              </button>
            </div>

            <label className="mt-4 block text-sm font-semibold text-slate-600">
              Target role or interview purpose
              <input
                value={targetRole}
                onChange={(event) => setTargetRole(event.target.value)}
                className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-3 text-base text-slate-900 outline-none transition focus:border-calm focus:ring-4 focus:ring-calm/15"
              />
            </label>

            <label className="mt-4 block text-sm font-semibold text-slate-600">
              Japanese work log
              <textarea
                value={workLog}
                onChange={(event) => setWorkLog(event.target.value)}
                rows={7}
                placeholder="今日の仕事ログを貼る。会社名、顧客名、案件名、正確な数字は伏せる。"
                className="mt-2 w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-3 text-base leading-relaxed text-slate-900 outline-none transition focus:border-calm focus:ring-4 focus:ring-calm/15"
              />
            </label>

            <div className="mt-4">
              <p className="text-sm font-semibold text-slate-600">Focus sound</p>
              <div className="mt-2 grid grid-cols-3 gap-2 sm:grid-cols-9">
                {focusSounds.map((sound) => (
                  <button
                    type="button"
                    key={sound}
                    onClick={() => setFocusSound(sound)}
                    className={[
                      "min-h-11 rounded-lg px-2 text-sm font-bold ring-1 transition",
                      focusSound === sound
                        ? "bg-calm text-white ring-calm"
                        : "bg-white text-slate-700 ring-slate-200 hover:bg-slate-50"
                    ].join(" ")}
                  >
                    {sound}
                  </button>
                ))}
              </div>
              <p className="mt-2 rounded-lg bg-honey/20 px-3 py-2 text-sm leading-relaxed text-slate-700">
                {focusSoundCues[focusSound]}
              </p>
            </div>

            <button
              type="button"
              onClick={handleGenerateMaterials}
              disabled={!canGenerate}
              className="mt-5 w-full rounded-full bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition active:scale-[0.99] disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {flowState === "generating" ? "Generating..." : "Generate 30-second practice"}
            </button>
          </section>

          {materials && (flowState === "materials" || flowState === "recording" || flowState === "processing") && (
            <section className="rounded-lg bg-white p-5 shadow-soft ring-1 ring-white/80">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-bold text-calm">{materials.topic}</p>
                  <h2 className="mt-1 text-xl font-bold leading-tight text-slate-950">
                    30-second answer
                  </h2>
                </div>
                <span className="rounded-full bg-coral/10 px-3 py-1 text-xs font-bold text-coral">
                  {materials.focusSound}
                </span>
              </div>

              {materials.privacyWarnings.length > 0 && (
                <div className="mt-4 rounded-lg bg-coral/10 px-3 py-3 text-sm leading-relaxed text-slate-700">
                  {materials.privacyWarnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              )}

              <ul className="mt-4 grid gap-2 text-sm leading-relaxed text-slate-700">
                {materials.summaryBullets.map((bullet) => (
                  <li key={bullet} className="rounded-lg bg-slate-50 px-3 py-2">
                    {bullet}
                  </li>
                ))}
              </ul>

              <p className="mt-4 text-2xl font-bold leading-snug text-slate-950">
                {materials.answer30}
              </p>
              <p className="mt-3 rounded-lg bg-calm-soft px-3 py-3 text-sm leading-relaxed text-slate-800">
                {materials.answer30Ipa}
              </p>
              <p className="mt-3 rounded-lg bg-white px-3 py-3 text-sm leading-relaxed text-slate-700 ring-1 ring-slate-100">
                Read this out loud, then answer the question below in your own
                words. This MVP does not use API text-to-speech.
              </p>

              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg bg-honey/20 p-4">
                  <p className="text-sm font-bold text-slate-900">Question to answer</p>
                  <p className="mt-2 text-base font-semibold leading-snug text-slate-800">
                    {materials.questions[0]}
                  </p>
                </div>
                <div className="rounded-lg bg-slate-50 p-4">
                  <p className="text-sm font-bold text-slate-900">Repair phrase</p>
                  <p className="mt-2 text-base font-semibold leading-snug text-slate-800">
                    {materials.repairPhrases[0]}
                  </p>
                </div>
              </div>

              <div className="mt-5 rounded-lg bg-white px-4 pb-4 pt-2 shadow-sm ring-1 ring-slate-100">
                <WaveformIndicator
                  active={flowState === "recording"}
                  subdued={flowState === "processing"}
                />
                <MicButton
                  state={micState}
                  onPress={handleMicPress}
                  disabled={showPrivacyNotice}
                  idleLabel="録音して文字起こしレビュー"
                  recordingLabel="録音中..."
                  processingLabel="文字起こししてレビュー中..."
                />
                <button
                  type="button"
                  onClick={handleQuietReview}
                  className="mt-4 w-full rounded-full bg-white px-5 py-3 text-sm font-bold text-slate-600 ring-1 ring-slate-200 transition active:scale-[0.99]"
                >
                  Finish with quiet mode
                </button>
              </div>
            </section>
          )}

          {materials && review && flowState === "review" && (
            <section className="rounded-lg bg-white p-5 shadow-soft ring-1 ring-white/80">
              <p className="text-sm font-bold uppercase tracking-[0.08em] text-calm">
                Whisperにこう聞こえました
              </p>
              <h2 className="mt-2 text-2xl font-bold text-slate-950">
                伝わり方レビューを保存します。
              </h2>
              {reviewMode === "recording" && transcriptPreview && (
                <div className="mt-4 rounded-lg bg-slate-50 px-3 py-3">
                  <p className="text-sm font-bold text-slate-900">
                    Whisper transcript
                  </p>
                  <p className="mt-2 text-base leading-relaxed text-slate-700">
                    {transcriptPreview}
                  </p>
                </div>
              )}
              <p className="mt-4 rounded-lg bg-calm-soft px-3 py-3 text-sm font-semibold leading-relaxed text-slate-800">
                {review.positive}
              </p>
              <div className="mt-4 grid gap-3">
                {review.fixPoints.map((fixPoint) => (
                  <p
                    key={fixPoint}
                    className="rounded-lg bg-slate-50 px-3 py-3 text-sm leading-relaxed text-slate-700"
                  >
                    {fixPoint}
                  </p>
                ))}
              </div>
              <p className="mt-4 rounded-lg bg-honey/20 px-3 py-3 text-sm leading-relaxed text-slate-700">
                {review.structureSuggestion}
              </p>
              <p className="mt-3 rounded-lg bg-white px-3 py-3 text-sm leading-relaxed text-slate-700 ring-1 ring-slate-100">
                <span className="font-bold text-slate-900">重点音メモ: </span>
                {review.focusSoundNote}
              </p>
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => handleCompleteSession(reviewMode)}
                  className="rounded-full bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition active:scale-[0.99]"
                >
                  Save session
                </button>
                <button
                  type="button"
                  onClick={handleQuietReview}
                  className="rounded-full bg-white px-5 py-3 text-sm font-bold text-slate-600 ring-1 ring-slate-200 transition active:scale-[0.99]"
                >
                  Refresh review
                </button>
              </div>
            </section>
          )}

          {flowState === "complete" && latestSession && (
            <section className="rounded-lg bg-white p-5 text-center shadow-soft ring-1 ring-white/80">
              <p className="text-sm font-bold uppercase tracking-[0.08em] text-calm">
                Done for today
              </p>
              <h2 className="mt-2 text-2xl font-bold text-slate-950">
                One interview answer saved.
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-slate-600">
                Next focus: {latestSession.review.nextFocus}. You have saved{" "}
                {progress.interviewSessions.length} interview practice{" "}
                {progress.interviewSessions.length === 1 ? "session" : "sessions"}.
              </p>
              <button
                type="button"
                onClick={handleStartNew}
                className="mt-5 w-full rounded-full bg-calm px-5 py-3 text-sm font-bold text-white shadow-sm transition active:scale-[0.99]"
              >
                Start another log
              </button>
            </section>
          )}

          {statusMessage && (
            <p className="rounded-lg bg-white px-4 py-3 text-sm font-medium text-slate-600 shadow-sm">
              {statusMessage}
            </p>
          )}
        </div>
      </div>

      {showPrivacyNotice && (
        <div className="fixed inset-0 z-40 flex items-end bg-slate-950/30 px-4 pb-4 backdrop-blur-sm sm:items-center sm:justify-center">
          <section className="mx-auto w-full max-w-md rounded-lg bg-white p-6 shadow-soft">
            <p className="text-sm font-bold uppercase tracking-[0.08em] text-calm">
              AI privacy note
            </p>
            <h2 className="mt-2 text-2xl font-bold leading-tight text-slate-950">
              Keep work details abstract.
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              This MVP sends the typed work log to the server-side material
              generation route. Replace customer names, company names, project
              names, and exact internal numbers before generating practice.
            </p>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              Raw audio is used only for the current review attempt and is not
              stored in localStorage. Saved sessions keep generated material and
              review notes, not the original work log.
            </p>
            <p className="mt-3 text-sm leading-relaxed text-slate-600">
              Interview recordings are transcribed with Groq Whisper when
              configured. This is a transcript-based communication review, not a
              precise acoustic measurement.
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
    </main>
  );
}

function getSttFailureMessage(code?: SttErrorCode) {
  switch (code) {
    case "not_configured":
      return "録音レビューはまだ設定されていません。GROQ_API_KEYを設定するか、quiet modeを使ってください。";
    case "missing_audio":
    case "empty_audio":
      return "録音が空でした。もう一度録音するか、今日はquiet modeで完了してください。";
    case "too_short":
      return "録音が短すぎました。もう一度録音するか、今日はquiet modeで完了してください。";
    case "too_large":
      return "録音が25MBを超えています。短く録音し直すか、今日はquiet modeで完了してください。";
    case "unsupported_format":
      return "このブラウザの録音形式はMVP対象外です。Chrome/Edgeで録音するか、今日はquiet modeで完了してください。";
    case "failed":
    default:
      return "Whisper文字起こしに失敗しました。音声は保存していません。もう一度録音してください。";
  }
}
