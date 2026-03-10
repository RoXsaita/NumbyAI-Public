import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { BRAND_RED, TOTAL_FRAMES } from "../constants";

export const AnimatedBorder: React.FC = () => {
  const frame = useCurrentFrame();

  const rotation = frame * 0.5;

  const opacity = interpolate(
    frame,
    [0, 140, 160, TOTAL_FRAMES - 150, TOTAL_FRAMES - 100],
    [0, 0, 0.6, 0.6, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const glowIntensity = 1 + Math.sin(frame * 0.04) * 0.3;

  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity }}>
      {/* Top edge */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 2,
          background: `linear-gradient(90deg, 
            transparent, 
            ${BRAND_RED}${Math.round(40 * glowIntensity).toString(16).padStart(2, "0")} 20%, 
            ${BRAND_RED}${Math.round(70 * glowIntensity).toString(16).padStart(2, "0")} 50%, 
            ${BRAND_RED}${Math.round(40 * glowIntensity).toString(16).padStart(2, "0")} 80%, 
            transparent
          )`,
          boxShadow: `0 0 ${8 * glowIntensity}px ${BRAND_RED}33`,
        }}
      />

      {/* Bottom edge */}
      <div
        style={{
          position: "absolute",
          bottom: 3,
          left: 0,
          right: 0,
          height: 1,
          background: `linear-gradient(90deg, 
            transparent, 
            ${BRAND_RED}${Math.round(30 * glowIntensity).toString(16).padStart(2, "0")} 30%, 
            ${BRAND_RED}${Math.round(50 * glowIntensity).toString(16).padStart(2, "0")} 50%, 
            ${BRAND_RED}${Math.round(30 * glowIntensity).toString(16).padStart(2, "0")} 70%, 
            transparent
          )`,
        }}
      />

      {/* Left edge */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          bottom: 0,
          width: 2,
          background: `linear-gradient(180deg, 
            transparent, 
            ${BRAND_RED}${Math.round(25 * glowIntensity).toString(16).padStart(2, "0")} 20%, 
            ${BRAND_RED}${Math.round(50 * glowIntensity).toString(16).padStart(2, "0")} 50%, 
            ${BRAND_RED}${Math.round(25 * glowIntensity).toString(16).padStart(2, "0")} 80%, 
            transparent
          )`,
        }}
      />

      {/* Right edge */}
      <div
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          bottom: 0,
          width: 2,
          background: `linear-gradient(180deg, 
            transparent, 
            ${BRAND_RED}${Math.round(25 * glowIntensity).toString(16).padStart(2, "0")} 20%, 
            ${BRAND_RED}${Math.round(50 * glowIntensity).toString(16).padStart(2, "0")} 50%, 
            ${BRAND_RED}${Math.round(25 * glowIntensity).toString(16).padStart(2, "0")} 80%, 
            transparent
          )`,
        }}
      />

      {/* Corner accents */}
      {[
        { top: -1, left: -1 },
        { top: -1, right: -1 },
        { bottom: 2, left: -1 },
        { bottom: 2, right: -1 },
      ].map((pos, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            ...pos,
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: BRAND_RED,
            boxShadow: `0 0 ${12 * glowIntensity}px ${BRAND_RED}88`,
            opacity: 0.5 * glowIntensity,
          } as React.CSSProperties}
        />
      ))}
    </AbsoluteFill>
  );
};
