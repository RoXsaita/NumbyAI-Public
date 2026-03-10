import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { TOTAL_FRAMES, BRAND_RED } from "../constants";

interface Particle {
  id: number;
  startX: number;
  startY: number;
  speed: number;
  size: number;
  opacity: number;
  drift: number;
  phase: number;
}

function seededRandom(seed: number): number {
  const x = Math.sin(seed * 127.1) * 43758.5453;
  return x - Math.floor(x);
}

interface ParticleFieldProps {
  opacity?: number;
}

export const ParticleField: React.FC<ParticleFieldProps> = ({
  opacity = 0.15,
}) => {
  const frame = useCurrentFrame();

  const particles = useMemo<Particle[]>(() => {
    const result: Particle[] = [];
    for (let i = 0; i < 30; i++) {
      result.push({
        id: i,
        startX: seededRandom(i * 3 + 1) * 100,
        startY: seededRandom(i * 3 + 2) * 100,
        speed: 0.02 + seededRandom(i * 3 + 3) * 0.06,
        size: 1 + seededRandom(i * 3 + 4) * 3,
        opacity: 0.2 + seededRandom(i * 3 + 5) * 0.6,
        drift: (seededRandom(i * 3 + 6) - 0.5) * 0.3,
        phase: seededRandom(i * 3 + 7) * Math.PI * 2,
      });
    }
    return result;
  }, []);

  const globalOpacity = interpolate(
    frame,
    [0, 120, 160, TOTAL_FRAMES - 150, TOTAL_FRAMES - 100],
    [0, 0, opacity, opacity, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: globalOpacity }}>
      {particles.map((p) => {
        const y = (p.startY + frame * p.speed) % 110 - 5;
        const x =
          p.startX + Math.sin(frame * 0.02 + p.phase) * 3 + frame * p.drift;
        const flickerOpacity =
          p.opacity * (0.6 + Math.sin(frame * 0.05 + p.phase) * 0.4);

        const isRed = p.id % 5 === 0;

        return (
          <div
            key={p.id}
            style={{
              position: "absolute",
              left: `${((x % 100) + 100) % 100}%`,
              top: `${y}%`,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              background: isRed ? BRAND_RED : "#fff",
              opacity: flickerOpacity,
              boxShadow: isRed
                ? `0 0 ${p.size * 3}px ${BRAND_RED}66`
                : `0 0 ${p.size * 2}px rgba(255,255,255,0.3)`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};
