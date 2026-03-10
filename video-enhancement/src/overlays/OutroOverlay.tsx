import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Easing,
} from "remotion";
import { BRAND_RED, BRAND_DARK, TOTAL_FRAMES } from "../constants";

export const OutroOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const relativeFrame = frame - (TOTAL_FRAMES - 150);

  const backdropOpacity = interpolate(relativeFrame, [0, 40, 150], [0, 1, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const logoScale = spring({
    frame: Math.max(0, relativeFrame - 30),
    fps,
    config: { damping: 12, stiffness: 80, mass: 0.8 },
  });

  const titleSlide = spring({
    frame: Math.max(0, relativeFrame - 40),
    fps,
    config: { damping: 14, stiffness: 100, mass: 0.6 },
  });

  const ctaSlide = spring({
    frame: Math.max(0, relativeFrame - 60),
    fps,
    config: { damping: 14, stiffness: 80, mass: 0.7 },
  });

  const urlOpacity = interpolate(relativeFrame, [80, 100], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const pulseScale =
    1 + Math.sin(relativeFrame * 0.08) * 0.02;

  return (
    <AbsoluteFill
      style={{
        opacity: backdropOpacity,
        background: `radial-gradient(ellipse at 50% 45%, #1a1a2e 0%, ${BRAND_DARK} 70%)`,
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
          gap: 16,
        }}
      >
        {/* Logo */}
        <div
          style={{
            width: 90,
            height: 90,
            borderRadius: "50%",
            background: BRAND_RED,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transform: `scale(${logoScale * pulseScale})`,
            boxShadow: `0 0 80px ${BRAND_RED}55, 0 0 160px ${BRAND_RED}22`,
          }}
        >
          <span
            style={{
              fontSize: 40,
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
            fontSize: 64,
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

        {/* CTA */}
        <div
          style={{
            marginTop: 8,
            transform: `translateY(${interpolate(ctaSlide, [0, 1], [20, 0])}px)`,
            opacity: ctaSlide,
          }}
        >
          <div
            style={{
              padding: "14px 40px",
              borderRadius: 12,
              background: BRAND_RED,
              boxShadow: `0 0 40px ${BRAND_RED}44`,
            }}
          >
            <span
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: "#fff",
                fontFamily: "system-ui, -apple-system, sans-serif",
                letterSpacing: "0.5px",
              }}
            >
              Try It Free — Open Source
            </span>
          </div>
        </div>

        {/* URL */}
        <p
          style={{
            fontSize: 20,
            color: "#64748B",
            fontFamily: "monospace",
            margin: 0,
            marginTop: 16,
            opacity: urlOpacity,
            letterSpacing: "1px",
          }}
        >
          github.com/RoXsaita/NumbyAI-Public
        </p>

        {/* Star badge */}
        <div
          style={{
            display: "flex",
            gap: 24,
            marginTop: 12,
            opacity: urlOpacity,
          }}
        >
          {["⭐ Star on GitHub", "🔒 100% Local", "🤖 AI-Powered"].map(
            (label) => (
              <div
                key={label}
                style={{
                  padding: "6px 16px",
                  borderRadius: 100,
                  border: "1px solid #334155",
                }}
              >
                <span
                  style={{
                    fontSize: 14,
                    color: "#94A3B8",
                    fontFamily: "system-ui, -apple-system, sans-serif",
                  }}
                >
                  {label}
                </span>
              </div>
            ),
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
};
