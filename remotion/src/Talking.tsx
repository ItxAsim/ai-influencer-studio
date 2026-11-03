import React from 'react';
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

export const FPS = 30;

export type CaptionLine = {text: string; from: number; to: number}; // seconds

export type TalkingProps = {
  video: string; // lip-synced clip, relative to public/
  voice: string; // clean voice-over, relative to public/
  lines: CaptionLine[];
  hook: string; // on-screen title for the first seconds; '' for none
  durationSeconds: number;
  ambientVolume: number; // 0 = no ambient bed
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const FONT = '"Helvetica Neue", Helvetica, Arial, "DejaVu Sans", sans-serif';

// Slow push-in plus a slight handheld sway, as if the propped phone breathes.
const Camera: React.FC<{children: React.ReactNode}> = ({children}) => {
  const f = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const t = f / durationInFrames;
  const scale = interpolate(t, [0, 1], [1.02, 1.08]);
  const x = 4 * Math.sin(t * Math.PI * 2 * 0.7);
  const y = 3 * Math.sin(t * Math.PI * 2 * 1.1 + 1);
  const rot = 0.25 * Math.sin(t * Math.PI * 2 * 0.5);
  return (
    <AbsoluteFill
      style={{transform: `translate(${x}px, ${y}px) rotate(${rot}deg) scale(${scale})`, transformOrigin: '50% 40%'}}
    >
      {children}
    </AbsoluteFill>
  );
};

// One subtitle line: words pop in one after another, the line fades out at its end.
// A dark box behind it keeps it readable over light clothes and bright backgrounds.
const Line: React.FC<{line: CaptionLine}> = ({line}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const start = line.from * fps;
  const end = line.to * fps;
  if (f < start - 1 || f > end + 6) return null;

  const words = line.text.split(' ');
  const perWord = Math.min(5, ((end - start) * 0.45) / words.length);
  const out = interpolate(f, [end - 4, end + 4], [1, 0], clamp);

  return (
    <div
      style={{
        alignSelf: 'center',
        maxWidth: 920,
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        gap: '0 16px',
        padding: '16px 32px 20px',
        borderRadius: 22,
        backgroundColor: 'rgba(12,16,10,0.62)',
        opacity: out,
      }}
    >
      {words.map((w, i) => {
        const s = spring({frame: f - start - i * perWord, fps, config: {damping: 16, stiffness: 180}});
        return (
          <span
            key={i}
            style={{
              display: 'inline-block',
              opacity: s,
              transform: `translateY(${(1 - s) * 18}px)`,
              color: '#fff',
              fontFamily: FONT,
              fontWeight: 700,
              fontSize: 60,
              lineHeight: 1.2,
              letterSpacing: -0.5,
            }}
          >
            {w}
          </span>
        );
      })}
    </div>
  );
};

// The hook title at the top for the first few seconds.
const Hook: React.FC<{text: string}> = ({text}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const s = spring({frame: f - 4, fps, config: {damping: 15, stiffness: 150}});
  const out = interpolate(f, [3.6 * fps, 4.2 * fps], [1, 0], clamp);
  if (!text || f > 4.2 * fps) return null;
  return (
    <AbsoluteFill style={{alignItems: 'center', paddingTop: 210}}>
      <div
        style={{
          maxWidth: 900,
          padding: '22px 36px',
          borderRadius: 26,
          backgroundColor: '#fff',
          color: '#111',
          fontFamily: FONT,
          fontWeight: 800,
          fontSize: 64,
          lineHeight: 1.12,
          textAlign: 'center',
          opacity: s * out,
          transform: `scale(${0.85 + s * 0.15}) rotate(-1.5deg)`,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

export const Talking: React.FC<TalkingProps> = ({video, voice, lines, hook, ambientVolume}) => {
  const {durationInFrames} = useVideoConfig();
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <Camera>
        <OffthreadVideo src={staticFile(video)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </Camera>

      <AbsoluteFill
        style={{background: 'linear-gradient(0deg, rgba(0,0,0,0.45) 0%, rgba(0,0,0,0) 32%)', pointerEvents: 'none'}}
      />

      <Hook text={hook} />

      <AbsoluteFill style={{justifyContent: 'flex-end', paddingBottom: 300}}>
        {lines.map((l, i) => (
          <Line key={i} line={l} />
        ))}
      </AbsoluteFill>

      <Audio src={staticFile(voice)} />
      {ambientVolume > 0 && (
        <Audio
          src={staticFile('audio/ambient.wav')}
          loop
          volume={(fr) =>
            ambientVolume *
            interpolate(fr, [0, 8], [0, 1], clamp) *
            interpolate(fr, [durationInFrames - 10, durationInFrames], [1, 0], clamp)
          }
        />
      )}
    </AbsoluteFill>
  );
};
