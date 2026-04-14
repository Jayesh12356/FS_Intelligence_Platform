"use client";

export function SkeletonText({ width = "100%", height = 14 }: { width?: string | number; height?: number }) {
  return <div className="skeleton skeleton-text" style={{ width, height }} />;
}

export function SkeletonCard({ height = 120 }: { height?: number }) {
  return <div className="skeleton skeleton-card" style={{ height }} />;
}

export function SkeletonCircle({ size = 40 }: { size?: number }) {
  return <div className="skeleton skeleton-circle" style={{ width: size, height: size }} />;
}

export function KpiRowSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="kpi-row">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="kpi-card" style={{ minHeight: 88 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
            <SkeletonText width="60%" height={12} />
            <SkeletonText width="40%" height={24} />
          </div>
          <SkeletonCircle size={48} />
        </div>
      ))}
    </div>
  );
}

export function CardListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} height={72} />
      ))}
    </div>
  );
}

export default function PageSkeleton() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <SkeletonText width={120} height={12} />
        <SkeletonText width={280} height={28} />
      </div>
      <KpiRowSkeleton />
      <SkeletonCard height={300} />
    </div>
  );
}
