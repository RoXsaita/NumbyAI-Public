import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
} from "remotion";
import { BRAND_RED, BRAND_DARK } from "../constants";

export const IntroOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const backdropOpacity = interpolate(frame, [0, 10, 90, 140], [1, 0.85, 0.85, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const logoScale = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 80, mass: 0.8 },
    delay: 5,
  });

  const titleSlide = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 100, mass: 0.6 },
    delay: 15,
  });

  const subtitleSlide = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 80, mass: 0.7 },
    delay: 25,
  });

  const taglineOpacity = interpolate(frame, [35, 50], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const exitY = interpolate(frame, [100, 140], [0, -60], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.4, 0, 0.2, 1),
  });

  const exitOpacity = interpolate(frame, [100, 130], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        opacity: backdropOpacity,
        background: `radial-gradient(ellipse at 50% 40%, ${BRAND_DARK}ee 0%, ${BRAND_DARK} 70%)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 12,
          transform: `translateY(${exitY}px)`,
          opacity: exitOpacity,
        }}
      >
        {/* Logo mark */}
        <div
          style={{
            width: 80,
            height: 80,
            borderRadius: "50%",
            background: BRAND_RED,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transform: `scale(${logoScale})`,
            boxShadow: `0 0 60px ${BRAND_RED}66, 0 0 120px ${BRAND_RED}33`,
          }}
        >
          <span
            style={{
              fontSize: 36,
              fontWeight: 900,
              color: "#fff",
              fontFamily: "system-ui, -apple-system, sans-serif",
            }}
          >
            N
          </span>
        </div>

        {/* Title */}
        <h1
          style={{
            fontSize: 72,
            fontWeight: 800,
            color: "#fff",
            fontFamily: "system-ui, -apple-system, sans-serif",
            letterSpacing: "-2px",
            margin: 0,
            transform: `translateY(${interpolate(titleSlide, [0, 1], [30, 0])}px)`,
            opacity: titleSlide,
          }}
        >
          <span style={{ color: BRAND_RED }}>Numby</span>AI
        </h1>

        {/* Subtitle */}
        <p
          style={{
            fontSize: 28,
            fontWeight: 400,
            color: "#94A3B8",
            fontFamily: "system-ui, -apple-system, sans-serif",
            margin: 0,
            letterSpacing: "0.5px",
            transform: `translateY(${interpolate(subtitleSlide, [0, 1], [20, 0])}px)`,
            opacity: subtitleSlide,
          }}
        >
          AI-Powered Finance Budgeting
        </p>

        {/* Tagline */}
        <div
          style={{
            marginTop: 20,
            padding: "8px 24px",
            borderRadius: 100,
            border: "1px solid #334155",
            opacity: taglineOpacity,
          }}
        >
          <span
            style={{
              fontSize: 16,
              color: "#64748B",
              fontFamily: "system-ui, -apple-system, sans-serif",
              letterSpacing: "3px",
              textTransform: "uppercase",
            }}
          >
            Open Source • Local AI • Privacy First
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
