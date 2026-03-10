import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  interpolate,
} from "remotion";
import { TOTAL_FRAMES, ZOOM_KEYFRAMES } from "../constants";
import { getInterpolatedZoom } from "../utils/zoom";

export const CursorSpotlight: React.FC = () => {
  const frame = useCurrentFrame();

  const { originX, originY, scale } = getInterpolatedZoom(frame, 30, ZOOM_KEYFRAMES);

  const isZoomed = scale > 1.05;

  const spotlightOpacity = interpolate(
    scale,
    [1, 1.15, 1.4],
    [0, 0.08, 0.15],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const globalFade = interpolate(
    frame,
    [0, 150, TOTAL_FRAMES - 120, TOTAL_FRAMES],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  if (!isZoomed) return null;

  const pulse = 1 + Math.sin(frame * 0.08) * 0.15;

  return (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        opacity: globalFade,
      }}
    >
      {/* Radial highlight at zoom origin */}
      <div
        style={{
          position: "absolute",
          left: `${originX}%`,
          top: `${originY}%`,
          width: 400 * pulse,
          height: 400 * pulse,
          borderRadius: "50%",
          background: `radial-gradient(circle, rgba(255,255,255,${spotlightOpacity}) 0%, transparent 70%)`,
          transform: "translate(-50%, -50%)",
        }}
      />
    </AbsoluteFill>
  );
};
