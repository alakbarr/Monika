// ==============================================================================
// File: src/lib/soundEffects.ts
// Description: Monika Matte Acoustic Tactile Audio Synthesizer (Web Audio API)
// ==============================================================================

class SoundEngine {
  private ctx: AudioContext | null = null;
  private isMuted: boolean = false;
  private masterGain: GainNode | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('monika_audio_muted');
      this.isMuted = stored === 'true';
    }
  }

  private initContext(): AudioContext | null {
    if (typeof window === 'undefined') return null;
    if (!this.ctx) {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
        this.masterGain = this.ctx.createGain();
        this.masterGain.gain.value = this.isMuted ? 0 : 0.65;
        this.masterGain.connect(this.ctx.destination);
      }
    }
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume().catch(() => {});
    }
    return this.ctx;
  }

  public unlock(): void {
    const ctx = this.initContext();
    if (ctx && ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
  }

  public toggleMute(): boolean {
    this.isMuted = !this.isMuted;
    if (this.masterGain && this.ctx) {
      this.masterGain.gain.setValueAtTime(this.isMuted ? 0 : 0.65, this.ctx.currentTime);
    }
    try {
      if (typeof window !== 'undefined') {
        localStorage.setItem('monika_audio_muted', String(this.isMuted));
      }
    } catch {}
    return this.isMuted;
  }

  public getMuted(): boolean {
    return this.isMuted;
  }

  /**
   * Synthesize a soft matte acoustic tactile click.
   */
  public playClick(type: 'typewriter' | 'shutter' | 'toggle' | 'bell' = 'typewriter'): void {
    if (this.isMuted) return;
    try {
      const ctx = this.initContext();
      if (!ctx) return;

      const now = ctx.currentTime;

      if (type === 'typewriter' || type === 'toggle') {
        // Low-frequency damped sine pulse (matte key switch)
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(220, now);
        osc.frequency.exponentialRampToValueAtTime(75, now + 0.024);

        gain.gain.setValueAtTime(0.055, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.024);

        osc.connect(gain);
        gain.connect(this.masterGain || ctx.destination);

        osc.start(now);
        osc.stop(now + 0.026);
      } else if (type === 'shutter') {
        // Soft sub-bass acoustic thud for drawer/sheet transitions
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(160, now);
        osc.frequency.exponentialRampToValueAtTime(55, now + 0.038);

        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.038);

        osc.connect(gain);
        gain.connect(this.masterGain || ctx.destination);

        osc.start(now);
        osc.stop(now + 0.042);
      } else if (type === 'bell') {
        // Warm harmonic confirmation tone
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, now);

        gain.gain.setValueAtTime(0.05, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);

        osc.connect(gain);
        gain.connect(this.masterGain || ctx.destination);

        osc.start(now);
        osc.stop(now + 0.24);
      }
    } catch {
      // Ignore audio synthesis errors on restricted platforms
    }
  }

  /**
   * Two-note low-register caution tone for safety alerts.
   */
  public playAlert(): void {
    if (this.isMuted) return;
    try {
      const ctx = this.initContext();
      if (!ctx) return;
      const now = ctx.currentTime;

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'triangle';
      osc.frequency.setValueAtTime(523.25, now); // C5
      osc.frequency.setValueAtTime(392.0, now + 0.09); // G4

      gain.gain.setValueAtTime(0.065, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);

      osc.connect(gain);
      gain.connect(this.masterGain || ctx.destination);

      osc.start(now);
      osc.stop(now + 0.24);
    } catch {}
  }

  /**
   * Subtle ascending fifth chime for trade execution.
   */
  public playTradeChime(): void {
    if (this.isMuted) return;
    try {
      const ctx = this.initContext();
      if (!ctx) return;
      const now = ctx.currentTime;

      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.setValueAtTime(880.0, now + 0.085); // A5

      gain.gain.setValueAtTime(0.065, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.32);

      osc.connect(gain);
      gain.connect(this.masterGain || ctx.destination);

      osc.start(now);
      osc.stop(now + 0.35);
    } catch {}
  }
}

export const sounds = new SoundEngine();

if (typeof window !== 'undefined') {
  const unlockAudio = () => {
    sounds.unlock();
    window.removeEventListener('pointerdown', unlockAudio);
    window.removeEventListener('keydown', unlockAudio);
  };
  window.addEventListener('pointerdown', unlockAudio, { once: true });
  window.addEventListener('keydown', unlockAudio, { once: true });
}
