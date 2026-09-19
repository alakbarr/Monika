import React from 'react';
import { AnalogDial } from '../ui/AnalogDial';

interface WinRateGaugeProps {
  winRate: number; // 0-100
  label?: string;
  size?: number;
}

export const WinRateGauge: React.FC<WinRateGaugeProps> = ({
  winRate,
  label = 'WIN RATE',
  size = 140,
}) => {
  return (
    <AnalogDial
      value={winRate}
      min={0}
      max={100}
      label={label}
      unit="%"
      size={size}
      dangerZone={45}
      dangerInverted={true}
    />
  );
};
