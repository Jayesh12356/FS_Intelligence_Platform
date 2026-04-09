"use client";

import "./globals.css";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

const NAV_ITEMS = [
  { label: "Upload FS", href: "/upload", icon: "⬆" },
  { label: "My Documents", href: "/documents", icon: "📄" },
  { label: "Analysis", href: "/analysis", icon: "🔍" },
  { label: "Library", href: "/library", icon: "📚" },
  { label: "Monitoring", href: "/monitoring", icon: "📡" },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const saved = localStorage.getItem("fsp-theme") as "dark" | "light" | null;
    if (saved) {
      setTheme(saved);
      document.documentElement.setAttribute("data-theme", saved);
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("fsp-theme", next);
  };

  return (
    <html lang="en" data-theme={theme}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>FS Intelligence Platform</title>
        <meta
          name="description"
          content="AI-powered platform that transforms Functional Specification documents into dev-ready task breakdowns"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="app-container">
          <nav className="nav" id="main-nav">
            <div className="nav-inner">
              <Link href="/" className="nav-brand">
                <span className="nav-brand-icon">◈</span>
                FS Intelligence
              </Link>

              <ul className="nav-links">
                {NAV_ITEMS.map((item) => (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={`nav-link ${
                        pathname === item.href ? "active" : ""
                      }`}
                      id={`nav-${item.href.slice(1)}`}
                    >
                      {item.icon} {item.label}
                    </Link>
                  </li>
                ))}
              </ul>

              <div className="nav-actions">
                <button
                  className="theme-toggle"
                  onClick={toggleTheme}
                  aria-label="Toggle theme"
                  id="theme-toggle"
                >
                  {theme === "dark" ? "☀" : "🌙"}
                </button>
              </div>
            </div>
          </nav>

          <main className="main-content">{children}</main>
        </div>
      </body>
    </html>
  );
}
