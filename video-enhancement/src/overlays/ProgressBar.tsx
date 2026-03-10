import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { TOTAL_FRAMES, BRAND_RED } from "../constants";

export const ProgressBar: React.FC = () => {
  const frame = useCurrentFrame();

  const progress = (frame / TOTAL_FRAMES) * 100;

  const opacity = interpolate(frame, [0, 60, TOTAL_FRAMES - 90, TOTAL_FRAMES - 30], [0, 0.8, 0.8, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const shimmerX = (frame * 3) % 300 - 100;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* Track */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 3,
          background: "rgba(255,255,255,0.08)",
          opacity,
        }}
      >
        {/* Fill */}
        <div
          style={{
            height: "100%",
            width: `${progress}%`,
            background: `linear-gradient(90deg, ${BRAND_RED}88, ${BRAND_RED})`,
            borderRadius: "0 2px 2px 0",
            position: "relative",
            overflow: "hidden",
          }}
        >
          {/* Shimmer */}
          <div
            style={{
              position: "absolute",
              top: 0,
              left: `${shimmerX}%`,
              width: "30%",
              height: "100%",
              background:
                "linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)",
            }}
          />
        </div>

        {/* Glow dot at tip */}
        <div
          style={{
            position: "absolute",
            bottom: -2,
            left: `${progress}%`,
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: BRAND_RED,
            boxShadow: `0 0 10px ${BRAND_RED}, 0 0 20px ${BRAND_RED}88`,
            transform: "translateX(-50%)",
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
