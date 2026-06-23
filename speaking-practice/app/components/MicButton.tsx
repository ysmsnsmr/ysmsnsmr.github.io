import type { MicState } from "@/types/speaking";

type MicButtonProps = {
  state: MicState;
  onPress: () => void;
  disabled?: boolean;
  idleLabel?: string;
  recordingLabel?: string;
  processingLabel?: string;
};

const labels: Record<MicState, string> = {
  idle: "Tap to speak",
  arming: "Get ready",
  recording: "Listening...",
  processing: "Checking your sentence..."
};

export default function MicButton({
  state,
  onPress,
  disabled,
  idleLabel,
  recordingLabel,
  processingLabel
}: MicButtonProps) {
  const isRecording = state === "recording";
  const isBusy = state === "arming" || state === "processing";
  const label =
    state === "idle" && idleLabel
      ? idleLabel
      : state === "recording" && recordingLabel
        ? recordingLabel
        : state === "processing" && processingLabel
          ? processingLabel
          : labels[state];

  return (
    <div className="flex flex-col items-center">
      <button
        type="button"
        onClick={onPress}
        disabled={disabled || state === "processing"}
        className={[
          "relative flex h-24 w-24 items-center justify-center rounded-full text-white shadow-soft transition",
          "focus:outline-none focus:ring-4 focus:ring-calm/25",
          isRecording ? "bg-coral ring-8 ring-coral/20" : "bg-calm ring-8 ring-calm-soft",
          isBusy ? "scale-95 opacity-80" : "active:scale-95",
          disabled || state === "processing" ? "cursor-not-allowed" : ""
        ].join(" ")}
        aria-label={label}
      >
        {isRecording && (
          <span className="absolute inset-0 animate-ping rounded-full bg-coral/35" />
        )}
        <span className="relative flex h-11 w-8 flex-col items-center justify-end">
          <span className="h-8 w-5 rounded-full border-2 border-white" />
          <span className="-mt-1 h-3 w-0.5 bg-white" />
          <span className="h-0.5 w-7 rounded-full bg-white" />
        </span>
      </button>
      <p className="mt-3 min-h-5 text-center text-sm font-semibold text-slate-700">
        {label}
      </p>
      {isRecording && (
        <p className="text-xs text-slate-500">Tap the mic when you are done.</p>
      )}
    </div>
  );
}
