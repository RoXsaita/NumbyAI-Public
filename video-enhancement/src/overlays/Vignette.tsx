import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";

interface VignetteProps {
  intensity?: number;
}

export const Vignette: React.FC<VignetteProps> = ({ intensity = 0.4 }) => {
  const frame = useCurrentFrame();

  const breathe = 1 + Math.sin(frame * 0.015) * 0.05;
  const effectiveIntensity = intensity * breathe;

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(
          ellipse 80% 70% at 50% 50%,
          transparent 50%,
          rgba(0, 0, 0, ${effectiveIntensity * 0.3}) 70%,
          rgba(0, 0, 0, ${effectiveIntensity * 0.7}) 85%,
          rgba(0, 0, 0, ${effectiveIntensity}) 100%
        )`,
        pointerEvents: "none",
      }}
    />
  );
};
