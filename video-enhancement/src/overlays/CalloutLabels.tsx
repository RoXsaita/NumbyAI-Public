import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
} from "remotion";
import { CALLOUT_LABELS, BRAND_RED, CalloutLabel } from "../constants";

const SingleCallout: React.FC<{ label: CalloutLabel }> = ({ label }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const relativeFrame = frame - label.startFrame;
  const duration = label.endFrame - label.startFrame;

  if (frame < label.startFrame || frame > label.endFrame) return null;

  const enterProgress = spring({
    frame: relativeFrame,
    fps,
    config: { damping: 15, stiffness: 120, mass: 0.5 },
  });

  const exitStart = duration - 20;
  const exitOpacity = interpolate(
    relativeFrame,
    [exitStart, duration],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const slideX = interpolate(enterProgress, [0, 1], [40, 0]);

  const isLeft =
    label.position === "bottom-left" || label.position === "top-left";
  const isBottom =
    label.position === "bottom-left" || label.position === "bottom-right";

  const positionStyle: React.CSSProperties = {
    position: "absolute",
    ...(isLeft ? { left: 40 } : { right: 40 }),
    ...(isBottom ? { bottom: 70 } : { top: 40 }),
  };

  const accentBarPulse = 1 + Math.sin(relativeFrame * 0.12) * 0.15;

  return (
    <div
      style={{
        ...positionStyle,
        transform: `translateX(${isLeft ? -slideX : slideX}px)`,
        opacity: enterProgress * exitOpacity,
        display: "flex",
        alignItems: "center",
        gap: 14,
        pointerEvents: "none",
      }}
    >
      {/* Accent bar */}
      <div
        style={{
          width: 4,
          height: 48,
          borderRadius: 4,
          background: BRAND_RED,
          boxShadow: `0 0 ${12 * accentBarPulse}px ${BRAND_RED}66`,
          opacity: accentBarPulse,
        }}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {/* Icon + main text */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {label.icon && (
            <span style={{ fontSize: 20 }}>{label.icon}</span>
          )}
          <span
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: "#fff",
              fontFamily: "system-ui, -apple-system, sans-serif",
              textShadow: "0 2px 8px rgba(0,0,0,0.6), 0 0 20px rgba(0,0,0,0.4)",
              letterSpacing: "-0.3px",
            }}
          >
            {label.text}
          </span>
        </div>

        {/* Subtext */}
        {label.subtext && (
          <span
            style={{
              fontSize: 15,
              fontWeight: 400,
              color: "#CBD5E1",
              fontFamily: "system-ui, -apple-system, sans-serif",
              textShadow: "0 1px 6px rgba(0,0,0,0.5)",
              letterSpacing: "0.2px",
            }}
          >
            {label.subtext}
          </span>
        )}
      </div>
    </div>
  );
};

export const CalloutLabels: React.FC = () => {
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {CALLOUT_LABELS.map((label, i) => (
        <SingleCallout key={i} label={label} />
      ))}
    </AbsoluteFill>
  );
};
