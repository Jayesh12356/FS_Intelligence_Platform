import Link from "next/link";

export default function NotFound() {
  return (
    <div
      style={{
        minHeight: "60vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1rem",
      }}
    >
      <div style={{ textAlign: "center", maxWidth: 520 }}>
        <div
          style={{
            fontSize: "3.5rem",
            fontWeight: 700,
            letterSpacing: "-0.02em",
            color: "var(--text-primary)",
          }}
        >
          404
        </div>
        <h1 style={{ fontSize: "1.25rem", margin: "0.5rem 0 0.75rem" }}>
          Page not found
        </h1>
        <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
          The page you requested doesn&apos;t exist, was moved, or is still being built.
        </p>
        <div style={{ display: "inline-flex", gap: "0.5rem" }}>
          <Link className="btn btn-primary" href="/">
            Back home
          </Link>
          <Link className="btn" href="/documents">
            Documents
          </Link>
        </div>
      </div>
    </div>
  );
}
