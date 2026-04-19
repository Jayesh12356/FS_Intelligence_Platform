"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Upload, FileUp, CheckCircle2, AlertCircle, X } from "lucide-react";
import { PageShell, FadeIn } from "@/components/index";
import { uploadFile, listProjects, uploadFileToProject } from "@/lib/api";
import type { FSProject } from "@/lib/api";

type UploadState = "idle" | "uploading" | "success" | "error";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ALLOWED_EXT = [".pdf", ".docx", ".txt"];
const ALLOWED_MIME = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "text/plain",
  "",
]);

function validateFile(file: File): string | null {
  const ext = file.name.toLowerCase().slice(file.name.lastIndexOf("."));
  if (!ALLOWED_EXT.includes(ext)) {
    return `Unsupported file type '${ext}'. Allowed: ${ALLOWED_EXT.join(", ")}`;
  }
  if (file.type && !ALLOWED_MIME.has(file.type)) {
    return `Unexpected content type '${file.type}' for ${ext} file.`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    const mb = (file.size / 1024 / 1024).toFixed(1);
    return `File is ${mb} MB — exceeds the 20 MB limit.`;
  }
  return null;
}

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [projects, setProjects] = useState<FSProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [progress, setProgress] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listProjects()
      .then((res) => setProjects(res.data?.projects || []))
      .catch(() => {});
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      const validationError = validateFile(file);
      if (validationError) {
        setSelectedFile(file);
        setUploadState("error");
        setStatusMessage(validationError);
        return;
      }

      setSelectedFile(file);
      setUploadState("uploading");
      setStatusMessage(`Uploading ${file.name}…`);
      setProgress(0);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        const result = selectedProjectId
          ? await uploadFileToProject(file, selectedProjectId)
          : await uploadFile(file);
        setUploadState("success");
        setStatusMessage(`Uploaded successfully: ${result.data.filename}`);
        setProgress(100);

        setTimeout(() => {
          router.push(`/documents/${result.data.id}`);
        }, 1200);
      } catch (err: unknown) {
        if ((err as Error)?.name === "AbortError") {
          setUploadState("idle");
          setStatusMessage("Upload cancelled.");
          return;
        }
        setUploadState("error");
        const message =
          err instanceof Error ? err.message : "Upload failed. Please try again.";
        setStatusMessage(message);
      } finally {
        abortRef.current = null;
      }
    },
    [router, selectedProjectId]
  );

  const cancelUpload = useCallback(() => {
    abortRef.current?.abort();
  }, []);

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
          {projects.length > 0 && (
            <div className="upload-project-picker">
              <label className="form-label" htmlFor="project-select">
                Assign to Project <span className="muted">(optional)</span>
              </label>
              <select
                id="project-select"
                className="form-input"
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                onClick={(e) => e.stopPropagation()}
              >
                <option value="">No project (standalone)</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.document_count} docs)
                  </option>
                ))}
              </select>
            </div>
          )}

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
                    animate={{
                      width: progress > 0 ? `${progress}%` : ["0%", "70%", "40%", "90%", "65%"],
                    }}
                    transition={{
                      duration: progress > 0 ? 0.3 : 2.2,
                      repeat: progress > 0 ? 0 : Infinity,
                      ease: "easeInOut",
                    }}
                  />
                </div>
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={cancelUpload}
                aria-label="Cancel upload"
                style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
              >
                <X size={14} /> Cancel
              </button>
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
