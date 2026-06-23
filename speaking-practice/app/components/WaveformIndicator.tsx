type WaveformIndicatorProps = {
  active?: boolean;
  subdued?: boolean;
};

const bars = [16, 28, 20, 38, 24, 44, 30, 22, 36, 18, 32, 26, 40, 20, 34, 24];

export default function WaveformIndicator({
  active = false,
  subdued = false
}: WaveformIndicatorProps) {
  return (
    <div
      className="flex h-14 items-center justify-center gap-1"
      aria-hidden="true"
    >
      {bars.map((height, index) => (
        <span
          key={`${height}-${index}`}
          className={[
            "w-1.5 rounded-full transition-all duration-300",
            active ? "animate-pulse bg-calm" : "bg-slate-300",
            subdued ? "opacity-50" : "opacity-100"
          ].join(" ")}
          style={{ height: active ? height : Math.max(8, height * 0.35) }}
        />
      ))}
    </div>
  );
}
