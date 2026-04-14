"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, FileUp, CheckCircle2, AlertCircle } from "lucide-react";
import { PageShell, FadeIn } from "@/components/index";
import { uploadFile, listProjects, uploadFileToProject } from "@/lib/api";
import type { FSProject } from "@/lib/api";

type UploadState = "idle" | "uploading" | "success" | "error";

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [projects, setProjects] = useState<FSProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");

  useEffect(() => {
    listProjects()
      .then((res) => setProjects(res.data?.projects || []))
      .catch(() => {});
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      setSelectedFile(file);
      setUploadState("uploading");
      setStatusMessage(`Uploading ${file.name}…`);

      try {
        const result = selectedProjectId
          ? await uploadFileToProject(file, selectedProjectId)
          : await uploadFile(file);
        setUploadState("success");
        setStatusMessage(`Uploaded successfully: ${result.data.filename}`);

        setTimeout(() => {
          router.push(`/documents/${result.data.id}`);
        }, 1200);
      } catch (err: unknown) {
        setUploadState("error");
        const message =
          err instanceof Error ? err.message : "Upload failed. Please try again.";
        setStatusMessage(message);
      }
    },
    [router]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) void handleFile(file);
    },
    [handleFile]
  );

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const onDragLeave = () => setDragOver(false);

  const onFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const onZoneKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openFilePicker();
    }
  };

  return (
    <PageShell
      title="Upload Document"
      subtitle="Upload your Functional Specification for analysis"
    >
      <div className="upload-container">
        <FadeIn>
          <motion.div
            className={`upload-zone ${dragOver ? "drag-over" : ""}`}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onClick={openFilePicker}
            onKeyDown={onZoneKeyDown}
            id="upload-zone"
            role="button"
            tabIndex={0}
            animate={{ scale: dragOver ? 1.02 : 1 }}
            transition={{ type: "spring", stiffness: 400, damping: 25 }}
          >
            <div className="upload-icon">
              {dragOver ? (
                <FileUp size={40} strokeWidth={1.5} aria-hidden />
              ) : (
                <Upload size={40} strokeWidth={1.5} aria-hidden />
              )}
            </div>
            <h3>
              {selectedFile
                ? selectedFile.name
                : "Drop your file here or click to browse"}
            </h3>
            <p>Maximum file size: 20MB</p>
            <div className="file-types">
              <span className="file-type-badge">.PDF</span>
              <span className="file-type-badge">.DOCX</span>
              <span className="file-type-badge">.TXT</span>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={onFileSelect}
              style={{ display: "none" }}
              id="file-input"
            />
          </motion.div>
        </FadeIn>

        {projects.length > 0 && (
          <FadeIn>
            <div className="card" style={{ padding: "1rem", marginTop: "1rem" }}>
              <label className="form-label" htmlFor="project-select">
                Assign to Project (optional)
              </label>
              <select
                id="project-select"
                className="form-input"
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                style={{ maxWidth: 400 }}
              >
                <option value="">No project (standalone)</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.document_count} docs)
                  </option>
                ))}
              </select>
            </div>
          </FadeIn>
        )}

        <AnimatePresence mode="wait">
          {uploadState === "uploading" && (
            <motion.div
              key="loading"
              className="upload-status loading"
              id="upload-loading"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <div className="spinner" aria-hidden />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div>{statusMessage}</div>
                <div className="upload-progress" aria-hidden>
                  <motion.div
                    className="upload-progress-bar"
                    initial={{ width: "0%" }}
                    animate={{ width: ["0%", "70%", "40%", "90%", "65%"] }}
                    transition={{
                      duration: 2.2,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }}
                  />
                </div>
              </div>
            </motion.div>
          )}

          {uploadState === "success" && (
            <motion.div
              key="success"
              className="upload-status success"
              id="upload-success"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <motion.span
                initial={{ scale: 0, rotate: -45 }}
                animate={{ scale: 1, rotate: 0 }}
                transition={{ type: "spring", stiffness: 400, damping: 18 }}
                style={{ display: "flex", flexShrink: 0 }}
              >
                <CheckCircle2 size={22} strokeWidth={2} aria-hidden />
              </motion.span>
              {statusMessage}
            </motion.div>
          )}

          {uploadState === "error" && (
            <motion.div
              key="error"
              className="upload-status error"
              id="upload-error"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
            >
              <AlertCircle size={22} strokeWidth={2} aria-hidden />
              {statusMessage}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </PageShell>
  );
}
