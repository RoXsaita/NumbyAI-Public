import { interpolate, Easing } from "remotion";
import { ZoomKeyframe } from "../constants";

interface ZoomState {
  scale: number;
  originX: number;
  originY: number;
}

export function getInterpolatedZoom(
  frame: number,
  fps: number,
  keyframes: ZoomKeyframe[],
): ZoomState {
  if (keyframes.length === 0) {
    return { scale: 1, originX: 50, originY: 50 };
  }

  if (frame <= keyframes[0].startFrame) {
    return {
      scale: keyframes[0].scale,
      originX: keyframes[0].originX,
      originY: keyframes[0].originY,
    };
  }

  const last = keyframes[keyframes.length - 1];
  if (frame >= last.endFrame) {
    return {
      scale: last.scale,
      originX: last.originX,
      originY: last.originY,
    };
  }

  for (let i = 0; i < keyframes.length; i++) {
    const kf = keyframes[i];

    if (frame >= kf.startFrame && frame <= kf.endFrame) {
      return {
        scale: kf.scale,
        originX: kf.originX,
        originY: kf.originY,
      };
    }

    if (i < keyframes.length - 1) {
      const next = keyframes[i + 1];
      if (frame > kf.endFrame && frame < next.startFrame) {
        const transitionDuration = next.startFrame - kf.endFrame;
        const progress = interpolate(
          frame,
          [kf.endFrame, next.startFrame],
          [0, 1],
          {
            easing: Easing.bezier(0.25, 0.1, 0.25, 1),
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          },
        );

        return {
          scale: kf.scale + (next.scale - kf.scale) * progress,
          originX: kf.originX + (next.originX - kf.originX) * progress,
          originY: kf.originY + (next.originY - kf.originY) * progress,
        };
      }
    }
  }

  return { scale: 1, originX: 50, originY: 50 };
}
