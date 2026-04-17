"use client";

import "./globals.css";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { Upload, FileText, RotateCcw, BookOpen, Activity, FolderOpen, Sun, Moon, Menu, X, Zap, Sparkles, Settings } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ToastProvider } from "../components/Toaster";

const THEME_INIT = `
try {
  var t = localStorage.getItem('fsp-theme');
  if (!t) t = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', t);
} catch (e) {}
`;

const NAV_ITEMS = [
  { label: "Create", href: "/create", icon: Sparkles },
  { label: "Upload", href: "/upload", icon: Upload },
  { label: "Documents", href: "/documents", icon: FileText },
  { label: "Projects", href: "/projects", icon: FolderOpen },
  { label: "Reverse FS", href: "/reverse", icon: RotateCcw },
  { label: "Library", href: "/library", icon: BookOpen },
  { label: "Monitoring", href: "/monitoring", icon: Activity },
  { label: "Settings", href: "/settings", icon: Settings },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [theme, setTheme] = useState<"dark" | "light">("light");
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const attr = document.documentElement.getAttribute("data-theme");
    const t: "dark" | "light" = attr === "dark" ? "dark" : "light";
    setTheme(t);
  }, []);

  useEffect(() => { setMobileOpen(false); }, [pathname]);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("fsp-theme", next);
  };

  const isActive = (href: string) =>
    pathname === href || (href !== "/" && pathname.startsWith(href));

  return (
    <html lang="en" data-theme={theme} suppressHydrationWarning>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>FS Intelligence Platform</title>
        <meta name="description" content="AI-powered platform that transforms Functional Specification documents into dev-ready task breakdowns" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700;14..32,800&display=swap" rel="stylesheet" />
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>
        <ToastProvider>
        <div className="app-container">
          <nav className="nav">
            <div className="nav-inner">
              <Link href="/" className="nav-brand" style={{ textDecoration: "none" }}>
                <span className="nav-brand-icon"><Zap size={18} /></span>
                FS Intelligence
              </Link>

              <ul className="nav-links">
                {NAV_ITEMS.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(item.href);
                  return (
                    <li key={item.href} style={{ listStyle: "none" }}>
                      <Link href={item.href} className={`nav-link ${active ? "active" : ""}`}>
                        <Icon size={16} strokeWidth={active ? 2.2 : 1.8} />
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>

              <div className="nav-actions">
                <button className="theme-toggle" onClick={toggleTheme} aria-label="Toggle theme">
                  {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
                </button>
                <button
                  className="theme-toggle"
                  onClick={() => setMobileOpen(!mobileOpen)}
                  aria-label="Menu"
                  style={{ display: "none" }}
                  id="mobile-menu-btn"
                >
                  {mobileOpen ? <X size={16} /> : <Menu size={16} />}
                </button>
              </div>
            </div>
          </nav>

          {/* Mobile menu */}
          <AnimatePresence>
            {mobileOpen && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
                style={{
                  position: "fixed", top: 52, left: 0, right: 0, zIndex: 99,
                  background: "var(--bg-card)", borderBottom: "1px solid var(--border-subtle)",
                  boxShadow: "var(--shadow-lg)", padding: "0.5rem",
                }}
              >
                {NAV_ITEMS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`nav-link ${isActive(item.href) ? "active" : ""}`}
                      style={{ display: "flex", padding: "0.75rem 1rem", width: "100%" }}
                    >
                      <Icon size={16} /> {item.label}
                    </Link>
                  );
                })}
              </motion.div>
            )}
          </AnimatePresence>

          <main className="main-content">{children}</main>
        </div>
        </ToastProvider>

        <style>{`
          @media (max-width: 768px) {
            #mobile-menu-btn { display: flex !important; }
          }
        `}</style>
      </body>
    </html>
  );
}
