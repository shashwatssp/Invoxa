/**
 * The Invoxa brand mark: a white spark-dot "i".
 *
 * Vector twin of the PNG app icons (icon-512.png etc.): the dot of the
 * "i" is the same four-pointed spark as the Ask AI tab icon, sitting on
 * the brand gradient supplied by the container's CSS background.
 */
export function BrandMark() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden focusable="false">
      <polygon
        points="12,5.3 12.61,7.42 14.76,8.03 12.61,8.64 12,10.79 11.39,8.64 9.24,8.03 11.39,7.42"
        fill="currentColor"
      />
      <rect x="10.44" y="10.9" width="3.12" height="8.3" rx="1.56" fill="currentColor" />
    </svg>
  );
}
