import { brandLogoForSurface, type BrandSurface } from "@/lib/brand";

type BrandLogoProps = {
  /** Set to the header/footer background: light = dark logo, dark = white logo */
  surface?: BrandSurface;
  icon?: boolean;
  className?: string;
  width?: number;
  height?: number;
  alt?: string;
  loading?: "eager" | "lazy";
  fetchPriority?: "high" | "low" | "auto";
};

export function BrandLogo({
  surface = "light",
  icon = false,
  className,
  width,
  height,
  alt = "VoxBulk",
  loading,
  fetchPriority,
}: BrandLogoProps) {
  return (
    <img
      src={brandLogoForSurface(surface, icon)}
      alt={alt}
      width={width}
      height={height}
      loading={loading}
      fetchPriority={fetchPriority}
      decoding="async"
      className={className}
    />
  );
}
