"use client";

import { useState, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { uploadFile } from "@/lib/api";

type UploadState = "idle" | "uploading" | "success" | "error";

export default function UploadPage() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadState, setUploadState] = useState<UploadState>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setSelectedFile(file);
      setUploadState("uploading");
      setStatusMessage(`Uploading ${file.name}…`);

      try {
        const result = await uploadFile(file);
        setUploadState("success");
        setStatusMessage(`Uploaded successfully: ${result.data.filename}`);

        // Redirect after short delay
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
      if (file) handleFile(file);
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
    if (file) handleFile(file);
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="upload-container">
      <h1>Upload FS Document</h1>
      <p className="subtitle">
        Upload your Functional Specification to start AI-powered analysis.
      </p>

      <div
        className={`upload-zone ${dragOver ? "drag-over" : ""}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={openFilePicker}
        id="upload-zone"
        role="button"
        tabIndex={0}
      >
        <div className="upload-icon">📂</div>
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
      </div>

      {uploadState === "uploading" && (
        <div className="upload-status loading" id="upload-loading">
          <div className="spinner" />
          {statusMessage}
        </div>
      )}

      {uploadState === "success" && (
        <div className="upload-status success" id="upload-success">
          ✓ {statusMessage}
        </div>
      )}

      {uploadState === "error" && (
        <div className="upload-status error" id="upload-error">
          ✗ {statusMessage}
        </div>
      )}
    </div>
  );
}
