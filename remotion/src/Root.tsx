import React from 'react';
import {Composition} from 'remotion';
import {FPS, Talking, TalkingProps} from './Talking';

const defaults: TalkingProps = {
  video: 'video/talking.mp4',
  voice: 'audio/voice.wav',
  lines: [],
  hook: '',
  durationSeconds: 10,
  ambientVolume: 0.18,
};

export const Root: React.FC = () => (
  <Composition
    id="Talking"
    component={Talking}
    fps={FPS}
    width={1080}
    height={1920}
    durationInFrames={10 * FPS}
    defaultProps={defaults}
    // The real length comes from the voice-over, passed in with --props.
    calculateMetadata={({props}) => ({durationInFrames: Math.ceil(props.durationSeconds * FPS)})}
  />
);
