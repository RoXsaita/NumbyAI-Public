import React from "react";
import {
  AbsoluteFill,
  OffthreadVideo,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
  Audio,
} from "remotion";
import { VIDEO_SRC, ZOOM_KEYFRAMES, TOTAL_FRAMES } from "./constants";
import { getInterpolatedZoom } from "./utils/zoom";
import { IntroOverlay } from "./overlays/IntroOverlay";
import { OutroOverlay } from "./overlays/OutroOverlay";
import { Vignette } from "./overlays/Vignette";
import { CalloutLabels } from "./overlays/CalloutLabels";
import { ProgressBar } from "./overlays/ProgressBar";
import { AnimatedBorder } from "./overlays/AnimatedBorder";
import { ParticleField } from "./overlays/ParticleField";
import { CursorSpotlight } from "./overlays/CursorSpotlight";

export const NumbyAIDemo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const { scale, originX, originY } = getInterpolatedZoom(
    frame,
    fps,
    ZOOM_KEYFRAMES,
  );

  const introFadeOut =
    frame < 120 ? 1 : frame < 150 ? 1 - (frame - 120) / 30 : 0;

  const outroFadeIn =
    frame > TOTAL_FRAMES - 120
      ? (frame - (TOTAL_FRAMES - 120)) / 60
      : 0;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {/* Main video with zoom/pan */}
      <AbsoluteFill
        style={{
          transform: `scale(${scale})`,
          transformOrigin: `${originX}% ${originY}%`,
          willChange: "transform",
        }}
      >
        <OffthreadVideo
          src={staticFile("original.mp4")}
          style={{ width: "100%", height: "100%" }}
        />
      </AbsoluteFill>

      {/* Subtle particle field */}
      <ParticleField opacity={0.12} />

      {/* Animated gradient border frame */}
      <AnimatedBorder />

      {/* Cinematic vignette */}
      <Vignette intensity={0.45} />

      {/* Cursor spotlight glow */}
      <CursorSpotlight />

      {/* Callout labels */}
      <CalloutLabels />

      {/* Progress bar at bottom */}
      <ProgressBar />

      {/* Intro overlay */}
      {frame < 160 && <IntroOverlay />}

      {/* Outro overlay */}
      {frame > TOTAL_FRAMES - 150 && <OutroOverlay />}
    </AbsoluteFill>
  );
};
