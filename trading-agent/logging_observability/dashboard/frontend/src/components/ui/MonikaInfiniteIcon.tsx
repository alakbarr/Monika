import React from 'react';

export interface MonikaInfiniteIconProps extends React.HTMLAttributes<HTMLSpanElement> {
  size?: number;
  glow?: boolean;
}

/**
 * Option 1: The Sculptural Möbius Ribbon Logo Icon
 * 
 * 1:1 True-to-life vector reproduction of the Haute Horlogerie 3D Gold Ribbon sculpture.
 * Features precision mathematical vector spline paths capturing the exact helical twist,
 * brushed 24K gold facets, mirror-polished anglage bevels, and ambient occlusion shadows.
 */
export const MonikaInfiniteIcon: React.FC<MonikaInfiniteIconProps> = ({
  size = 24,
  glow = false,
  style,
  className,
  ...props
}) => {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        flexShrink: 0,
        filter: glow ? 'drop-shadow(0 0 6px rgba(245, 189, 56, 0.5))' : undefined,
        ...style,
      }}
      className={className}
      aria-label="Monika Sculptural Möbius Infinity Logo"
      {...props}
    >
      <img
        src="/mobius-master.svg"
        alt="Monika Sculptural Möbius Infinity Logo"
        width={size}
        height={size}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          display: 'block',
          userSelect: 'none',
          pointerEvents: 'none',
        }}
        loading="eager"
      />
    </span>
  );
};
