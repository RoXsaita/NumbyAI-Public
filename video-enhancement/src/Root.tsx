import React from "react";
import { Composition } from "remotion";
import { NumbyAIDemo } from "./NumbyAIDemo";

const FPS = 30;
const DURATION_FRAMES = 2189;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="NumbyAIDemo"
        component={NumbyAIDemo}
        durationInFrames={DURATION_FRAMES}
        fps={FPS}
        width={1920}
        height={1080}
      />
    </>
  );
};
